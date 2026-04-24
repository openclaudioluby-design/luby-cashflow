"""
Gerador de relatórios HTML e CSV para o luby-cashflow.
"""

import csv
import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

VERSION = "1.0.0"

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Luby Cashflow — {data_geracao}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          background: #f5f7fa; color: #1a202c; line-height: 1.6; }}
  .container {{ max-width: 1100px; margin: 0 auto; padding: 24px 16px; }}
  header {{ background: #1a365d; color: white; padding: 24px; border-radius: 8px; margin-bottom: 24px; }}
  header h1 {{ font-size: 1.8rem; font-weight: 700; }}
  header p {{ opacity: 0.8; font-size: 0.95rem; margin-top: 4px; }}
  .card {{ background: white; border-radius: 8px; padding: 20px; margin-bottom: 20px;
           box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
  .card h2 {{ font-size: 1.1rem; font-weight: 600; color: #2d3748; margin-bottom: 12px;
              padding-bottom: 8px; border-bottom: 2px solid #e2e8f0; }}
  .resumo {{ background: #ebf8ff; border-left: 4px solid #3182ce; padding: 16px;
             border-radius: 4px; white-space: pre-wrap; font-size: 0.95rem; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; }}
  th {{ background: #2d3748; color: white; padding: 10px 12px; text-align: left; font-weight: 500; }}
  td {{ padding: 9px 12px; border-bottom: 1px solid #e2e8f0; }}
  tr:hover td {{ background: #f7fafc; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .pos {{ color: #276749; font-weight: 600; }}
  .neg {{ color: #9b2c2c; font-weight: 600; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; }}
  .alta {{ background: #c6f6d5; color: #276749; }}
  .media {{ background: #fefcbf; color: #744210; }}
  .baixa {{ background: #fed7d7; color: #9b2c2c; }}
  .alertas {{ font-size: 0.8rem; color: #718096; }}
  ul.risk-list {{ list-style: none; padding: 0; }}
  ul.risk-list li {{ padding: 6px 0; border-bottom: 1px solid #e2e8f0; font-size: 0.92rem; }}
  ul.risk-list li:before {{ content: "⚠️ "; }}
  ul.rec-list {{ list-style: none; padding: 0; }}
  ul.rec-list li {{ padding: 6px 0; border-bottom: 1px solid #e2e8f0; font-size: 0.92rem; }}
  ul.rec-list li:before {{ content: "✅ "; }}
  .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  footer {{ text-align: center; color: #a0aec0; font-size: 0.8rem; margin-top: 24px; }}
  .erro-box {{ background: #fff5f5; border: 1px solid #fc8181; border-radius: 6px; padding: 12px;
               color: #9b2c2c; font-size: 0.9rem; }}
  @media (max-width: 640px) {{ .grid-2 {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>⚡ Luby Cashflow</h1>
    <p>Projeção de Fluxo de Caixa · Gerado em {data_geracao} · Fontes: {fontes}</p>
  </header>

  <div class="card">
    <h2>📋 Resumo Executivo</h2>
    {resumo_html}
  </div>

  <div class="card">
    <h2>📊 Projeção Mensal</h2>
    {tabela_html}
  </div>

  <div class="grid-2">
    <div class="card">
      <h2>⚠️ Principais Riscos</h2>
      {riscos_html}
    </div>
    <div class="card">
      <h2>✅ Recomendações</h2>
      {recomendacoes_html}
    </div>
  </div>

  <footer>
    luby-cashflow v{versao} · {timestamp}
  </footer>
</div>
</body>
</html>
"""


def _fmt_brl(valor: float) -> str:
    """Formata valor para BRL."""
    if valor is None:
        return "—"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fontes_usadas(entries: list[dict]) -> str:
    fontes = sorted({e.get("fonte", "?") for e in entries if e.get("fonte")})
    return ", ".join(fontes) if fontes else "N/D"


def _build_tabela(projecao_mensal: list[dict], entries: list[dict]) -> str:
    """Constrói HTML da tabela mensal."""
    from collections import defaultdict

    # Sumariza entries por período para complementar dados do Llama
    resumo = defaultdict(lambda: {
        "receita_contrato": 0.0,
        "receita_pipeline": 0.0,
        "custo": 0.0,
    })
    for e in entries:
        p = e.get("periodo", "")
        tipo = e.get("tipo", "")
        val = (e.get("valor_brl", 0) or 0) * (e.get("probabilidade", 1) or 1)
        if tipo == "receita_contrato":
            resumo[p]["receita_contrato"] += val
        elif tipo == "receita_pipeline":
            resumo[p]["receita_pipeline"] += val
        elif tipo in ("custo_projetado", "custo_realizado"):
            resumo[p]["custo"] += val

    if not projecao_mensal:
        # Usa apenas os dados locais
        periodos = sorted(resumo.keys())
        rows_html = ""
        for p in periodos:
            d = resumo[p]
            rec = d["receita_contrato"] + d["receita_pipeline"]
            custo = d["custo"]
            saldo = rec - custo
            saldo_cls = "pos" if saldo >= 0 else "neg"
            rows_html += f"""
      <tr>
        <td>{p}</td>
        <td class="num">{_fmt_brl(d['receita_contrato'])}</td>
        <td class="num">{_fmt_brl(d['receita_pipeline'])}</td>
        <td class="num">{_fmt_brl(custo)}</td>
        <td class="num {saldo_cls}">{_fmt_brl(saldo)}</td>
        <td><span class="badge media">media</span></td>
        <td></td>
      </tr>"""
    else:
        rows_html = ""
        for m in projecao_mensal:
            p = m.get("periodo", "")
            rec_total = m.get("receita_total", 0) or 0
            custo_total = m.get("custo_total", 0) or 0
            saldo = m.get("saldo", rec_total - custo_total)
            saldo_cls = "pos" if saldo >= 0 else "neg"
            conf = m.get("confianca", "media")
            alertas = m.get("alertas", [])
            d = resumo.get(p, {})

            alertas_html = ""
            if alertas:
                alertas_html = '<br><span class="alertas">' + " · ".join(alertas) + "</span>"

            rows_html += f"""
      <tr>
        <td>{p}{alertas_html}</td>
        <td class="num">{_fmt_brl(d.get('receita_contrato', 0))}</td>
        <td class="num">{_fmt_brl(d.get('receita_pipeline', 0))}</td>
        <td class="num">{_fmt_brl(custo_total)}</td>
        <td class="num {saldo_cls}">{_fmt_brl(saldo)}</td>
        <td><span class="badge {conf}">{conf}</span></td>
      </tr>"""

    return f"""
    <table>
      <thead>
        <tr>
          <th>Período</th>
          <th>Receita Contrato</th>
          <th>Pipeline (ponderada)</th>
          <th>Custo Projetado</th>
          <th>Saldo</th>
          <th>Confiança</th>
        </tr>
      </thead>
      <tbody>{rows_html}
      </tbody>
    </table>"""


def gerar(entries: list[dict], projecao: dict, config: dict) -> dict:
    """
    Gera relatório HTML e CSV.
    Retorna dict com chaves 'html' e 'csv' contendo os caminhos gerados.
    """
    base_dir = Path(config.get("_base_dir", "."))
    out_dir = base_dir / config["caminhos"]["relatorios"]
    out_dir.mkdir(parents=True, exist_ok=True)

    hoje = datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data_geracao = datetime.now().strftime("%d/%m/%Y %H:%M")

    html_path = out_dir / f"cashflow_{hoje}.html"
    csv_path = out_dir / f"cashflow_{hoje}.csv"

    fontes = _fontes_usadas(entries)
    projecao_mensal = projecao.get("projecao_mensal", [])
    resumo_exec = projecao.get("resumo_executivo", "")
    riscos = projecao.get("principais_riscos", [])
    recomendacoes = projecao.get("recomendacoes", [])

    # --- HTML ---
    if projecao.get("erro"):
        resumo_html = f'<div class="erro-box">⚠️ Projeção IA indisponível: {projecao["erro"]}</div>'
    else:
        resumo_html = f'<div class="resumo">{resumo_exec or "Sem resumo disponível."}</div>'

    tabela_html = _build_tabela(projecao_mensal, entries)

    riscos_html = (
        "<ul class='risk-list'>" + "".join(f"<li>{r}</li>" for r in riscos) + "</ul>"
        if riscos else "<p style='color:#a0aec0'>Nenhum risco identificado.</p>"
    )
    recomendacoes_html = (
        "<ul class='rec-list'>" + "".join(f"<li>{r}</li>" for r in recomendacoes) + "</ul>"
        if recomendacoes else "<p style='color:#a0aec0'>Nenhuma recomendação disponível.</p>"
    )

    html_content = HTML_TEMPLATE.format(
        data_geracao=data_geracao,
        fontes=fontes,
        resumo_html=resumo_html,
        tabela_html=tabela_html,
        riscos_html=riscos_html,
        recomendacoes_html=recomendacoes_html,
        versao=VERSION,
        timestamp=timestamp,
    )

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    logger.info(f"relatorio: HTML gerado em {html_path}")

    # --- CSV ---
    from collections import defaultdict
    resumo = defaultdict(lambda: {
        "receita_contrato": 0.0,
        "receita_pipeline": 0.0,
        "custo_projetado": 0.0,
        "custo_realizado": 0.0,
    })
    for e in entries:
        p = e.get("periodo", "")
        tipo = e.get("tipo", "")
        val = (e.get("valor_brl", 0) or 0) * (e.get("probabilidade", 1) or 1)
        if tipo in resumo[p]:
            resumo[p][tipo] += val

    csv_periodos = sorted(set(list(resumo.keys()) + [m.get("periodo", "") for m in projecao_mensal]))

    # Índice da projeção por período
    proj_idx = {m.get("periodo", ""): m for m in projecao_mensal}

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "periodo", "receita_contrato_brl", "receita_pipeline_ponderada_brl",
            "custo_projetado_brl", "custo_realizado_brl", "total_receita",
            "total_custo", "saldo", "confianca",
        ])
        for p in csv_periodos:
            if not p:
                continue
            d = resumo.get(p, {})
            rec = d.get("receita_contrato", 0) + d.get("receita_pipeline", 0)
            custo = d.get("custo_projetado", 0) + d.get("custo_realizado", 0)
            proj = proj_idx.get(p, {})
            saldo = proj.get("saldo", rec - custo)
            conf = proj.get("confianca", "media")
            writer.writerow([
                p,
                round(d.get("receita_contrato", 0), 2),
                round(d.get("receita_pipeline", 0), 2),
                round(d.get("custo_projetado", 0), 2),
                round(d.get("custo_realizado", 0), 2),
                round(rec, 2),
                round(custo, 2),
                round(saldo, 2),
                conf,
            ])

    logger.info(f"relatorio: CSV gerado em {csv_path}")
    return {"html": str(html_path), "csv": str(csv_path)}
