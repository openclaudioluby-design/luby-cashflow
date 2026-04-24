"""
Cliente Ollama local — envia dados consolidados para o llama3 gerar projeção de fluxo de caixa.
"""

import json
import logging
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)

PROMPT_TEMPLATE = """Você é um analista financeiro sênior da Luby Tecnologia.
Abaixo estão os dados consolidados de fluxo de caixa para os próximos meses.
Dados em JSON:
{json_consolidado}

Com base nesses dados, forneça em JSON:
{{
  "projecao_mensal": [
    {{"periodo": "YYYY-MM", "receita_total": float, "custo_total": float,
      "saldo": float, "confianca": "alta|media|baixa", "alertas": [string]}}
  ],
  "resumo_executivo": "string (3-4 linhas, português)",
  "principais_riscos": [string],
  "recomendacoes": [string]
}}
Responda APENAS com o JSON, sem texto adicional.
"""


def _consolidar(entries: list[dict]) -> dict:
    """
    Agrupa entries por período e tipo, calculando totais ponderados.
    Retorna dict estruturado para enviar ao modelo.
    """
    periodos = defaultdict(lambda: {
        "receita_contrato": 0.0,
        "receita_pipeline": 0.0,
        "custo_projetado": 0.0,
        "custo_realizado": 0.0,
        "num_clientes": set(),
    })

    for e in entries:
        p = e.get("periodo", "")
        tipo = e.get("tipo", "")
        valor_ponderado = (e.get("valor_brl", 0) or 0) * (e.get("probabilidade", 1) or 1)

        if tipo in ("receita_contrato", "receita_pipeline", "custo_projetado", "custo_realizado"):
            periodos[p][tipo] += valor_ponderado

        cliente = e.get("cliente")
        if cliente:
            periodos[p]["num_clientes"].add(cliente)

    consolidado = []
    for periodo in sorted(periodos.keys()):
        d = periodos[periodo]
        consolidado.append({
            "periodo": periodo,
            "receita_contrato_brl": round(d["receita_contrato"], 2),
            "receita_pipeline_ponderada_brl": round(d["receita_pipeline"], 2),
            "custo_projetado_brl": round(d["custo_projetado"], 2),
            "custo_realizado_brl": round(d["custo_realizado"], 2),
            "total_receita": round(d["receita_contrato"] + d["receita_pipeline"], 2),
            "total_custo": round(d["custo_projetado"] + d["custo_realizado"], 2),
            "num_clientes_pipeline": len(d["num_clientes"]),
        })

    return {"periodos": consolidado, "total_registros": len(entries)}


def _extract_json(text: str) -> Any:
    """Tenta extrair JSON da resposta do modelo."""
    import re

    # Tenta parse direto
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # Tenta extrair bloco JSON com regex
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return None


def gerar_projecao(entries: list[dict], config: dict) -> dict:
    """
    Envia dados consolidados ao Ollama/llama3 e retorna a projeção estruturada.

    Returns:
        dict com chaves: projecao_mensal, resumo_executivo, principais_riscos, recomendacoes
        Em caso de erro: dict com chave "erro" e dados brutos em "dados_brutos"
    """
    import requests

    base_url = config["ollama"]["base_url"].rstrip("/")
    model = config["ollama"]["model"]
    timeout = config["ollama"]["timeout_segundos"]

    consolidado = _consolidar(entries)

    if not consolidado["periodos"]:
        logger.warning("llama_client: Nenhum dado consolidado para enviar.")
        return {
            "projecao_mensal": [],
            "resumo_executivo": "Sem dados suficientes para gerar projeção.",
            "principais_riscos": ["Ausência de dados nas fontes configuradas."],
            "recomendacoes": ["Verificar configuração dos adaptadores e fontes de dados."],
        }

    json_consolidado = json.dumps(consolidado, ensure_ascii=False, indent=2)
    prompt = PROMPT_TEMPLATE.format(json_consolidado=json_consolidado)

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": 2048,
        },
    }

    logger.info(f"llama_client: Enviando {len(consolidado['periodos'])} períodos para {model}...")

    try:
        resp = requests.post(
            f"{base_url}/api/generate",
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        result = resp.json()
    except requests.exceptions.ConnectionError:
        logger.error(f"llama_client: Ollama não está rodando em {base_url}")
        return {
            "erro": f"Ollama não está disponível em {base_url}",
            "dados_consolidados": consolidado,
        }
    except Exception as e:
        logger.error(f"llama_client: Erro na chamada ao Ollama: {e}")
        return {
            "erro": str(e),
            "dados_consolidados": consolidado,
        }

    raw_response = result.get("response", "")
    logger.debug(f"llama_client: Resposta bruta: {raw_response[:200]}...")

    parsed = _extract_json(raw_response)
    if parsed is None:
        logger.warning("llama_client: Não foi possível parsear JSON da resposta.")
        return {
            "erro": "Parse JSON falhou",
            "dados_brutos": raw_response,
            "dados_consolidados": consolidado,
        }

    # Garante estrutura mínima
    parsed.setdefault("projecao_mensal", [])
    parsed.setdefault("resumo_executivo", "")
    parsed.setdefault("principais_riscos", [])
    parsed.setdefault("recomendacoes", [])

    logger.info(f"llama_client: Projeção gerada para {len(parsed['projecao_mensal'])} períodos.")
    return parsed
