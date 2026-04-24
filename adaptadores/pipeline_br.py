"""
Adaptador Pipeline BR — lê Google Sheets via gspread com service account.
Credenciais esperadas em: ~/.config/luby-cashflow/google_credentials.json
"""

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

CREDENTIALS_PATH = Path.home() / ".config" / "luby-cashflow" / "google_credentials.json"


def _find_col(headers: list[str], *keywords) -> Optional[int]:
    """Encontra índice de coluna cujo nome contém alguma das keywords (case-insensitive)."""
    for kw in keywords:
        for i, h in enumerate(headers):
            if kw.lower() in str(h).lower():
                return i
    return None


def _parse_valor(raw) -> Optional[float]:
    """Converte string monetária para float."""
    if raw is None or str(raw).strip() == "":
        return None
    try:
        cleaned = str(raw).replace("R$", "").replace("$", "").replace(".", "").replace(",", ".").strip()
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _parse_periodo(raw) -> Optional[str]:
    """Normaliza data/período para formato YYYY-MM."""
    if raw is None or str(raw).strip() == "":
        return None
    from datetime import datetime
    raw_str = str(raw).strip()
    # Tenta formatos comuns
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%Y", "%Y-%m", "%d-%m-%Y"):
        try:
            dt = datetime.strptime(raw_str[:len(fmt.replace("%Y","2000").replace("%m","01").replace("%d","01"))], fmt)
            return dt.strftime("%Y-%m")
        except ValueError:
            pass
    # Tenta extrair YYYY-MM de string longa
    import re
    m = re.search(r"(\d{4})[/-](\d{2})", raw_str)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    m = re.search(r"(\d{2})[/-](\d{4})", raw_str)
    if m:
        return f"{m.group(2)}-{m.group(1)}"
    return None


def coletar(config: dict) -> list:
    """
    Coleta dados do Pipeline BR via Google Sheets.
    Retorna list[CashflowEntry].
    """
    from schema import CashflowEntry, PIPELINE_BR_PROB

    sheet_id = config["sheets"]["pipeline_br_id"]
    aba = config["sheets"]["pipeline_br_aba"]

    if sheet_id.startswith("COLE_"):
        logger.warning("pipeline_br: ID da planilha não configurado, pulando.")
        return []

    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        logger.error("pipeline_br: gspread ou google-auth não instalados.")
        return []

    if not CREDENTIALS_PATH.exists():
        logger.error(f"pipeline_br: Credenciais não encontradas em {CREDENTIALS_PATH}")
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
        logger.error(f"pipeline_br: Erro ao acessar Sheets: {e}")
        return []

    if len(rows) < 2:
        logger.warning("pipeline_br: Planilha vazia ou sem dados.")
        return []

    headers = rows[0]
    data_rows = rows[1:]

    col_cliente = _find_col(headers, "cliente", "account", "empresa")
    col_valor = _find_col(headers, "valor", "amount", "receita")
    col_fase = _find_col(headers, "fase", "stage", "etapa")
    col_periodo = _find_col(headers, "mês", "mes", "data", "close", "fechamento")
    col_bu = _find_col(headers, "bu", "unidade")
    col_categoria = _find_col(headers, "categoria", "servico", "serviço", "produto")

    if col_valor is None:
        logger.error("pipeline_br: Coluna de valor não encontrada.")
        return []

    entries = []
    for i, row in enumerate(data_rows, start=2):
        def get(col):
            if col is None or col >= len(row):
                return None
            return row[col]

        valor = _parse_valor(get(col_valor))
        if valor is None or valor <= 0:
            logger.warning(f"pipeline_br: Linha {i} ignorada — valor inválido: {get(col_valor)!r}")
            continue

        periodo = _parse_periodo(get(col_periodo))
        if periodo is None:
            logger.warning(f"pipeline_br: Linha {i} ignorada — período inválido: {get(col_periodo)!r}")
            continue

        fase_raw = str(get(col_fase) or "").lower().strip()
        prob = PIPELINE_BR_PROB.get(fase_raw)
        if prob is None:
            # fuzzy: encontra a chave mais próxima
            for k, v in PIPELINE_BR_PROB.items():
                if k in fase_raw or fase_raw in k:
                    prob = v
                    break
            if prob is None:
                prob = 0.10  # default conservador
                logger.warning(f"pipeline_br: Fase desconhecida '{fase_raw}' na linha {i}, usando prob=0.10")

        confianca = "alta" if prob >= 0.85 else ("media" if prob >= 0.40 else "baixa")
        bu = str(get(col_bu) or "BR").strip().upper()
        if bu not in ("BR", "US"):
            bu = "BR"

        entry = CashflowEntry(
            periodo=periodo,
            bu=bu,
            tipo="receita_pipeline",
            categoria=str(get(col_categoria) or "Pipeline").strip() or "Pipeline",
            valor_brl=valor,
            probabilidade=prob,
            fonte="pipeline_br",
            confianca=confianca,
            cliente=str(get(col_cliente) or "").strip() or None,
            descricao=f"Fase: {fase_raw}",
        )
        entries.append(entry)

    logger.info(f"pipeline_br: {len(entries)} entries coletadas.")
    return entries
