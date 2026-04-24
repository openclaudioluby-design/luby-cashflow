"""
Adaptador RP/BI — lê planilha de custos projetados via Sheets ou arquivo local.
"""

import logging
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
    if raw is None or str(raw).strip() in ("", "nan"):
        return None
    try:
        cleaned = (
            str(raw)
            .replace("R$", "").replace("$", "")
            .replace(".", "").replace(",", ".")
            .strip()
        )
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _parse_periodo(raw) -> Optional[str]:
    if raw is None or str(raw).strip() in ("", "nat", "nan"):
        return None
    import re
    from datetime import datetime
    raw_str = str(raw).strip()
    if hasattr(raw, "strftime"):
        return raw.strftime("%Y-%m")
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%Y", "%Y-%m"):
        try:
            dt = datetime.strptime(raw_str, fmt)
            return dt.strftime("%Y-%m")
        except ValueError:
            pass
    m = re.search(r"(\d{4})[/-](\d{2})", raw_str)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    m = re.search(r"(\d{2})[/-](\d{4})", raw_str)
    if m:
        return f"{m.group(2)}-{m.group(1)}"
    return None


def _rows_to_entries(headers: list[str], data_rows: list[list]) -> list:
    from schema import CashflowEntry

    col_centro = _find_col(headers, "centro", "custo", "cost center")
    col_categoria = _find_col(headers, "categoria", "category", "tipo", "despesa")
    col_valor = _find_col(headers, "valor", "amount", "value", "total")
    col_periodo = _find_col(headers, "competencia", "competência", "mes", "mês", "periodo", "período", "data")
    col_bu = _find_col(headers, "bu", "unidade", "unit")

    if col_valor is None:
        logger.error("rp_bi: Coluna de valor não encontrada.")
        return []

    entries = []
    for i, row in enumerate(data_rows, start=2):
        def get(col):
            if col is None or col >= len(row):
                return None
            return row[col]

        valor = _parse_valor(get(col_valor))
        if valor is None or valor <= 0:
            logger.warning(f"rp_bi: Linha {i} ignorada — valor inválido")
            continue

        periodo = _parse_periodo(get(col_periodo))
        if periodo is None:
            logger.warning(f"rp_bi: Linha {i} ignorada — período inválido")
            continue

        bu = str(get(col_bu) or "BR").strip().upper()
        if bu not in ("BR", "US"):
            bu = "BR"

        categoria = str(get(col_categoria) or get(col_centro) or "Custo").strip() or "Custo"
        descricao = str(get(col_centro) or "").strip() or None

        entries.append(CashflowEntry(
            periodo=periodo,
            bu=bu,
            tipo="custo_projetado",
            categoria=categoria,
            valor_brl=valor,
            probabilidade=1.0,
            fonte="rp_bi",
            confianca="alta",
            cliente=None,
            descricao=descricao,
        ))

    return entries


def _coletar_sheets(config: dict) -> Optional[list]:
    """Tenta coletar via Google Sheets. Retorna None se não disponível."""
    sheet_id = config["sheets"].get("rp_bi_id", "")
    aba = config["sheets"].get("rp_bi_aba", "Projeção")

    if not sheet_id or sheet_id.startswith("COLE_"):
        return None

    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        return None

    if not CREDENTIALS_PATH.exists():
        return None

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
        logger.error(f"rp_bi: Erro ao acessar Sheets: {e}")
        return None

    if len(rows) < 2:
        return []

    headers = rows[0]
    return _rows_to_entries(headers, rows[1:])


def _coletar_arquivo(config: dict) -> list:
    """Fallback: procura arquivo rp_bi_*.csv ou rp_bi_*.xlsx na pasta de drop."""
    import pandas as pd

    drop_dir = Path(config.get("_base_dir", ".")) / config["caminhos"]["omie_drop"]
    arquivos = sorted(
        [f for f in drop_dir.iterdir() if f.is_file() and f.name.startswith("rp_bi")
         and f.suffix.lower() in (".csv", ".xlsx", ".xls")],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )

    if not arquivos:
        logger.warning("rp_bi: Nenhum arquivo rp_bi_* encontrado em omie_drop/")
        return []

    arq = arquivos[0]
    logger.info(f"rp_bi: Usando arquivo local {arq.name}")

    try:
        if arq.suffix.lower() in (".xlsx", ".xls"):
            df = pd.read_excel(arq, dtype=str)
        else:
            df = pd.read_csv(arq, dtype=str, sep=None, engine="python", encoding="utf-8", errors="replace")
    except Exception as e:
        logger.error(f"rp_bi: Erro ao ler {arq.name}: {e}")
        return []

    df.columns = [str(c).strip() for c in df.columns]
    headers = list(df.columns)
    data_rows = [list(row) for _, row in df.iterrows()]
    return _rows_to_entries(headers, data_rows)


def coletar(config: dict) -> list:
    """
    Coleta dados de custos do RP/BI.
    Tenta Sheets primeiro, depois fallback para arquivo local.
    Retorna list[CashflowEntry].
    """
    entries = _coletar_sheets(config)
    if entries is not None:
        logger.info(f"rp_bi: {len(entries)} entries via Sheets.")
        return entries

    logger.info("rp_bi: Sheets indisponível, tentando arquivo local...")
    entries = _coletar_arquivo(config)
    logger.info(f"rp_bi: {len(entries)} entries via arquivo local.")
    return entries
