"""
Adaptador OMIE — monitora pasta omie_drop/ por arquivos CSV/XLSX.
Arquivos processados são renomeados com prefixo processado_YYYY-MM-DD_.
"""

import logging
import os
from datetime import datetime, date
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


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
    raw_str = str(raw).strip()
    # pandas Timestamp
    if hasattr(raw, "strftime"):
        return raw.strftime("%Y-%m")
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%Y", "%Y-%m"):
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


def _detectar_sep(filepath: str) -> str:
    """Detecta separador CSV tentando ler primeiras linhas."""
    try:
        with open(filepath, encoding="utf-8", errors="replace") as f:
            sample = f.read(1024)
        semicolons = sample.count(";")
        commas = sample.count(",")
        return ";" if semicolons > commas else ","
    except Exception:
        return ","


def _processar_arquivo(filepath: Path, config: dict) -> list:
    """Processa um único arquivo OMIE e retorna list[CashflowEntry]."""
    import pandas as pd
    from schema import CashflowEntry

    try:
        if filepath.suffix.lower() in (".xlsx", ".xls"):
            df = pd.read_excel(filepath, dtype=str)
        else:
            sep = _detectar_sep(str(filepath))
            df = pd.read_csv(filepath, sep=sep, dtype=str, encoding="utf-8", errors="replace")
    except Exception as e:
        logger.error(f"omie: Erro ao ler {filepath.name}: {e}")
        return []

    df.columns = [str(c).strip() for c in df.columns]
    headers = list(df.columns)

    col_descricao = _find_col(headers, "contrato", "descricao", "descrição", "servico", "serviço")
    col_cliente = _find_col(headers, "cliente", "razao", "razão", "nome", "empresa")
    col_valor = _find_col(headers, "valor", "amount", "receita", "mensalidade")
    col_periodo = _find_col(headers, "vencimento", "competencia", "competência", "data", "mes", "mês")
    col_recorrente = _find_col(headers, "recorrente", "mensal", "recorrencia", "recorrência")

    if col_valor is None:
        logger.warning(f"omie: Coluna de valor não encontrada em {filepath.name}")
        return []

    entries = []
    for i, row in df.iterrows():
        def get(col):
            if col is None:
                return None
            return row.iloc[col] if col < len(row) else None

        valor = _parse_valor(get(col_valor))
        if valor is None or valor <= 0:
            logger.warning(f"omie: Linha {i+2} ignorada — valor inválido")
            continue

        periodo_raw = get(col_periodo)
        periodo = _parse_periodo(periodo_raw)
        if periodo is None:
            logger.warning(f"omie: Linha {i+2} ignorada — período inválido: {periodo_raw!r}")
            continue

        # Detecta se é recorrente mensal
        recorrente = False
        if col_recorrente is not None:
            rec_val = str(get(col_recorrente) or "").lower().strip()
            recorrente = rec_val in ("sim", "s", "yes", "y", "1", "true", "x")

        cliente = str(get(col_cliente) or "").strip() or None
        descricao = str(get(col_descricao) or "").strip() or None

        if recorrente:
            # Expande em 12 meses
            from datetime import datetime, timedelta
            try:
                base_dt = datetime.strptime(periodo, "%Y-%m")
            except ValueError:
                base_dt = datetime.now()
            for m in range(12):
                year = base_dt.year + (base_dt.month - 1 + m) // 12
                month = (base_dt.month - 1 + m) % 12 + 1
                p = f"{year:04d}-{month:02d}"
                entries.append(CashflowEntry(
                    periodo=p,
                    bu="BR",
                    tipo="receita_contrato",
                    categoria="Contrato Recorrente",
                    valor_brl=valor,
                    probabilidade=1.0,
                    fonte="omie",
                    confianca="alta",
                    cliente=cliente,
                    descricao=descricao,
                ))
        else:
            entries.append(CashflowEntry(
                periodo=periodo,
                bu="BR",
                tipo="receita_contrato",
                categoria="Contrato",
                valor_brl=valor,
                probabilidade=1.0,
                fonte="omie",
                confianca="alta",
                cliente=cliente,
                descricao=descricao,
            ))

    return entries


def coletar(config: dict) -> list:
    """
    Monitora pasta omie_drop/ e processa arquivos novos.
    Retorna list[CashflowEntry].
    """
    drop_dir = Path(config.get("_base_dir", ".")) / config["caminhos"]["omie_drop"]
    drop_dir.mkdir(parents=True, exist_ok=True)

    hoje = date.today().strftime("%Y-%m-%d")
    arquivos = [
        f for f in drop_dir.iterdir()
        if f.is_file()
        and f.suffix.lower() in (".csv", ".xlsx", ".xls")
        and not f.name.startswith("processado_")
        and not f.name.startswith("rp_bi")
    ]

    if not arquivos:
        logger.info("omie: Nenhum arquivo novo na pasta de drop.")
        return []

    all_entries = []
    for arq in arquivos:
        logger.info(f"omie: Processando {arq.name}...")
        entries = _processar_arquivo(arq, config)
        logger.info(f"omie: {len(entries)} entries de {arq.name}")
        all_entries.extend(entries)

        # Marca como processado
        novo_nome = drop_dir / f"processado_{hoje}_{arq.name}"
        try:
            arq.rename(novo_nome)
        except Exception as e:
            logger.warning(f"omie: Não foi possível renomear {arq.name}: {e}")

    logger.info(f"omie: Total de {len(all_entries)} entries coletadas.")
    return all_entries
