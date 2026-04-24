#!/usr/bin/env python3
"""
luby-cashflow — Orquestrador principal.
Ponto de entrada do cron diário e execução manual.

Uso:
    python3 main.py           # execução normal
    python3 main.py --dry-run # usa dados mock, não acessa fontes reais
"""

import argparse
import logging
import os
import sys
import traceback
from datetime import datetime, date
from pathlib import Path

# ── Resolve base_dir: env LUBY_BASE_DIR > diretório do script ───────────────
BASE_DIR = Path(os.environ.get("LUBY_BASE_DIR", Path(__file__).parent)).resolve()
os.chdir(BASE_DIR)
sys.path.insert(0, str(BASE_DIR))


def _setup_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def _load_config() -> dict:
    import yaml
    config_path = BASE_DIR / "config" / "config.yaml"
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["_base_dir"] = str(BASE_DIR)
    return cfg


def _mock_entries() -> list:
    """Gera 3 entries por tipo para dry-run."""
    from schema import CashflowEntry
    from datetime import datetime

    hoje = datetime.now()
    entries = []
    for i in range(3):
        year = hoje.year
        month = (hoje.month + i - 1) % 12 + 1
        if hoje.month + i > 12:
            year += 1
        periodo = f"{year:04d}-{month:02d}"

        entries.append(CashflowEntry(
            periodo=periodo, bu="BR", tipo="receita_contrato",
            categoria="Contrato Mock", valor_brl=100000.0 + i * 10000,
            probabilidade=1.0, fonte="omie", confianca="alta",
            cliente=f"Cliente Mock {i+1}", descricao="[dry-run]",
        ))
        entries.append(CashflowEntry(
            periodo=periodo, bu="BR", tipo="receita_pipeline",
            categoria="Pipeline Mock", valor_brl=200000.0 + i * 20000,
            probabilidade=0.6, fonte="pipeline_br", confianca="media",
            cliente=f"Prospect Mock {i+1}", descricao="[dry-run]",
        ))
        entries.append(CashflowEntry(
            periodo=periodo, bu="US", tipo="receita_pipeline",
            categoria="Pipeline US Mock", valor_brl=150000.0 + i * 15000,
            probabilidade=0.4, fonte="pipeline_us", confianca="baixa",
            cliente=f"US Prospect {i+1}", descricao="[dry-run]",
        ))
        entries.append(CashflowEntry(
            periodo=periodo, bu="BR", tipo="custo_projetado",
            categoria="Custo Mock", valor_brl=80000.0 + i * 5000,
            probabilidade=1.0, fonte="rp_bi", confianca="alta",
            descricao="[dry-run]",
        ))

    return entries


def main(dry_run: bool = False) -> int:
    """
    Orquestrador principal.
    Retorna 0 em sucesso, 1 em falha fatal.
    """
    # 1. Carrega config
    try:
        config = _load_config()
    except Exception as e:
        print(f"[FATAL] Não foi possível carregar config/config.yaml: {e}")
        return 1

    # 2. Setup logging
    log_path = BASE_DIR / config["caminhos"]["log"]
    _setup_logging(log_path)
    logger = logging.getLogger("main")

    logger.info("=" * 60)
    logger.info(f"luby-cashflow iniciado {'[DRY-RUN]' if dry_run else ''}")
    logger.info(f"Base dir: {BASE_DIR}")

    try:
        # 3. Inicializa banco
        from db import init_db, salvar_entries, buscar_entries
        db_path = BASE_DIR / config["caminhos"]["historico"] / "cashflow.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        init_db(str(db_path))
        logger.info(f"Banco inicializado: {db_path}")

        # 4. Coleta dados dos adaptadores
        all_entries = []

        if dry_run:
            logger.info("DRY-RUN: usando dados mock")
            all_entries = _mock_entries()
            logger.info(f"Mock: {len(all_entries)} entries geradas")
        else:
            from adaptadores import pipeline_br, pipeline_us, omie, rp_bi

            adaptadores = [
                ("pipeline_br", pipeline_br.coletar),
                ("pipeline_us", pipeline_us.coletar),
                ("omie", omie.coletar),
                ("rp_bi", rp_bi.coletar),
            ]

            for nome, func in adaptadores:
                try:
                    entries = func(config)
                    logger.info(f"Adaptador [{nome}]: {len(entries)} entries")
                    all_entries.extend(entries)
                except Exception as e:
                    logger.error(f"Adaptador [{nome}] falhou: {e}")
                    logger.debug(traceback.format_exc())

        logger.info(f"Total de entries coletadas: {len(all_entries)}")

        # 5. Salva no banco
        n_saved = salvar_entries(all_entries, str(db_path))
        logger.info(f"Entries salvas no banco (novas): {n_saved}")

        # 6. Busca entries dos próximos 12 meses
        hoje = date.today()
        periodo_inicio = hoje.strftime("%Y-%m")
        fim_year = hoje.year + (1 if hoje.month > 1 else 0)
        fim_month = (hoje.month + 11 - 1) % 12 + 1
        fim_year = hoje.year + (hoje.month + 11 - 1) // 12
        periodo_fim = f"{fim_year:04d}-{fim_month:02d}"

        entries_db = buscar_entries(periodo_inicio, periodo_fim, str(db_path))
        logger.info(f"Entries para projeção ({periodo_inicio} → {periodo_fim}): {len(entries_db)}")

        # 7. Gera projeção com Llama
        from llama_client import gerar_projecao
        projecao = gerar_projecao(entries_db, config)

        if projecao.get("erro"):
            logger.warning(f"Projeção IA com erro: {projecao['erro']}")
        else:
            logger.info(f"Projeção gerada: {len(projecao.get('projecao_mensal', []))} períodos")

        # 8. Gera relatório
        from relatorio import gerar
        caminhos = gerar(entries_db, projecao, config)

        logger.info("=" * 60)
        logger.info("✅ Fluxo de caixa atualizado com sucesso!")
        logger.info(f"   📄 HTML: {caminhos['html']}")
        logger.info(f"   📊 CSV:  {caminhos['csv']}")
        logger.info("=" * 60)

        return 0

    except Exception as e:
        logging.getLogger("main").error(f"[FATAL] Erro inesperado: {e}")
        logging.getLogger("main").error(traceback.format_exc())
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="luby-cashflow — projeção de fluxo de caixa")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Usa dados mock, não acessa fontes reais nem Ollama",
    )
    args = parser.parse_args()
    sys.exit(main(dry_run=args.dry_run))
