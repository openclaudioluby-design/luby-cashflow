import sqlite3
from typing import Optional
from schema import CashflowEntry

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    periodo TEXT,
    bu TEXT,
    tipo TEXT,
    categoria TEXT,
    valor_brl REAL,
    probabilidade REAL,
    fonte TEXT,
    confianca TEXT,
    cliente TEXT,
    descricao TEXT,
    updated_at TEXT,
    UNIQUE(periodo, fonte, cliente, categoria)
);
"""

INSERT_SQL = """
INSERT OR IGNORE INTO entries
    (periodo, bu, tipo, categoria, valor_brl, probabilidade, fonte, confianca, cliente, descricao, updated_at)
VALUES
    (:periodo, :bu, :tipo, :categoria, :valor_brl, :probabilidade, :fonte, :confianca, :cliente, :descricao, :updated_at)
"""


def init_db(db_path: str) -> None:
    """Cria tabela entries se não existir."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(CREATE_TABLE_SQL)
        conn.commit()
    finally:
        conn.close()


def salvar_entries(entries: list, db_path: str) -> int:
    """
    Insere entries no banco, ignorando duplicatas por (periodo, fonte, cliente, categoria).
    Retorna o número de entries efetivamente inseridas.
    """
    if not entries:
        return 0

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        rows = [e.to_dict() if isinstance(e, CashflowEntry) else e for e in entries]
        cursor.executemany(INSERT_SQL, rows)
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def buscar_entries(periodo_inicio: str, periodo_fim: str, db_path: str) -> list[dict]:
    """
    Retorna lista de dicts filtrada por período (formato YYYY-MM).
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(
            "SELECT * FROM entries WHERE periodo >= ? AND periodo <= ? ORDER BY periodo, tipo, fonte",
            (periodo_inicio, periodo_fim),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def listar_periodos(db_path: str) -> list[str]:
    """Retorna lista de períodos distintos disponíveis no banco."""
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute("SELECT DISTINCT periodo FROM entries ORDER BY periodo")
        return [row[0] for row in cursor.fetchall()]
    finally:
        conn.close()
