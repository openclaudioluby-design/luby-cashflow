"""
Adaptador Pipeline US — lê Google Sheets via gspread, converte USD→BRL.
"""

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

CREDENTIALS_PATH = Path.home() / ".config" / "luby-cashflow" / "google_credentials.json"


def _find_col(headers: list[str], *keywords) -> Optional[int]:
    for kw in keywords:
        for i, h in enumerate(headers):
            if kw.lower() in str(h).lower():
                return i
    return None


def _parse_valor(raw) -> Optional[float]:
    if raw is None or str(raw).strip() == "":
        return None
    try:
        cleaned = (
            str(raw)
            .replace("$", "").replace("USD", "").replace("R$", "")
            .replace(",", "").replace(" ", "")
            .strip()
        )
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _parse_periodo(raw) -> Optional[str]:
    if raw is None or str(raw).strip() == "":
        return None
    from datetime import datetime
    import re
    raw_str = str(raw).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%m/%Y", "%Y-%m"):
        try:
            dt = datetime.strptime(raw_str, fmt)
            return dt.strftime("%Y-%m")
        except ValueError:
            pass
    m = re.search(r"(\d{4})[/-](\d{2})", raw_str)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return None


def _get_usd_brl(fallback: float) -> float:
    """Busca cotação USD/BRL em tempo real. Retorna fallback se falhar."""
    try:
        import requests
        resp = requests.get(
            "https://economia.awesomeapi.com.br/json/last/USD-BRL",
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        rate = float(data["USDBRL"]["bid"])
        logger.info(f"pipeline_us: Cotação USD/BRL = {rate}")
        return rate
    except Exception as e:
        logger.warning(f"pipeline_us: Falha ao buscar cotação USD/BRL ({e}), usando fallback {fallback}")
        return fallback


def coletar(config: dict) -> list:
    """
    Coleta dados do Pipeline US via Google Sheets.
    Retorna list[CashflowEntry].
    """
    from schema import CashflowEntry, PIPELINE_US_PROB

    sheet_id = config["sheets"]["pipeline_us_id"]
    aba = config["sheets"]["pipeline_us_aba"]
    usd_brl_fallback = config["cambio"]["usd_brl_padrao"]

    if sheet_id.startswith("COLE_"):
        logger.warning("pipeline_us: ID da planilha não configurado, pulando.")
        return []

    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        logger.error("pipeline_us: gspread ou google-auth não instalados.")
        return []

    if not CREDENTIALS_PATH.exists():
        logger.error(f"pipeline_us: Credenciais não encontradas em {CREDENTIALS_PATH}")
        return []

    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/drive.readonly",
        ]
        creds = Credentials.from_service_account_file(str(CREDENTIALS_PATH), scopes=scopes)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(sheet_id)
        ws = sh.worksheet(aba)
        rows = ws.get_all_values()
    except Exception as e:
        logger.error(f"pipeline_us: Erro ao acessar Sheets: {e}")
        return []

    if len(rows) < 2:
        logger.warning("pipeline_us: Planilha vazia ou sem dados.")
        return []

    usd_brl = _get_usd_brl(usd_brl_fallback)

    headers = rows[0]
    data_rows = rows[1:]

    col_cliente = _find_col(headers, "account", "cliente", "company", "empresa")
    col_valor = _find_col(headers, "amount", "valor", "value", "receita")
    col_fase = _find_col(headers, "stage", "fase", "etapa", "status")
    col_periodo = _find_col(headers, "close date", "close_date", "closedate", "data", "mes", "mês", "period")
    col_bu = _find_col(headers, "bu", "unit")
    col_categoria = _find_col(headers, "categoria", "category", "service", "servico", "produto")

    if col_valor is None:
        logger.error("pipeline_us: Coluna de valor não encontrada.")
        return []

    entries = []
    for i, row in enumerate(data_rows, start=2):
        def get(col):
            if col is None or col >= len(row):
                return None
            return row[col]

        valor_usd = _parse_valor(get(col_valor))
        if valor_usd is None or valor_usd <= 0:
            logger.warning(f"pipeline_us: Linha {i} ignorada — valor inválido: {get(col_valor)!r}")
            continue

        periodo = _parse_periodo(get(col_periodo))
        if periodo is None:
            logger.warning(f"pipeline_us: Linha {i} ignorada — período inválido: {get(col_periodo)!r}")
            continue

        fase_raw = str(get(col_fase) or "").lower().strip()
        prob = PIPELINE_US_PROB.get(fase_raw)
        if prob is None:
            for k, v in PIPELINE_US_PROB.items():
                if k in fase_raw or fase_raw in k:
                    prob = v
                    break
            if prob is None:
                prob = 0.10
                logger.warning(f"pipeline_us: Stage desconhecido '{fase_raw}' na linha {i}, usando prob=0.10")

        valor_brl = round(valor_usd * usd_brl, 2)
        confianca = "alta" if prob >= 0.85 else ("media" if prob >= 0.40 else "baixa")
        bu = str(get(col_bu) or "US").strip().upper()
        if bu not in ("BR", "US"):
            bu = "US"

        entry = CashflowEntry(
            periodo=periodo,
            bu=bu,
            tipo="receita_pipeline",
            categoria=str(get(col_categoria) or "Pipeline").strip() or "Pipeline",
            valor_brl=valor_brl,
            probabilidade=prob,
            fonte="pipeline_us",
            confianca=confianca,
            cliente=str(get(col_cliente) or "").strip() or None,
            descricao=f"Stage: {fase_raw} | USD {valor_usd:.2f} × {usd_brl}",
        )
        entries.append(entry)

    logger.info(f"pipeline_us: {len(entries)} entries coletadas.")
    return entries
