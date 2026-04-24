# luby-cashflow ⚡

Sistema automatizado de projeção de **fluxo de caixa** para a Luby Tecnologia.

Coleta dados de múltiplas fontes (Google Sheets, OMIE, RP/BI), normaliza, envia para análise via IA local (Ollama/llama3) e gera relatórios em HTML e CSV todos os dias às 7h.

---

## O que o sistema faz

1. **Coleta** dados de 3 fontes:
   - Pipeline BR e US (Google Sheets via API)
   - Exportações do OMIE (arquivos CSV/XLSX em pasta de drop)
   - Planilha RP/BI de custos projetados (Sheets ou arquivo local)

2. **Normaliza** tudo em um schema comum (`CashflowEntry`) com valores em BRL

3. **Analisa** com IA local (Ollama/llama3) para gerar projeção inteligente com alertas e recomendações

4. **Persiste** histórico em SQLite local (sem dependências externas de banco)

5. **Gera** relatório em HTML responsivo e CSV para os próximos 12 meses

6. **Executa automaticamente** via cron todo dia às 7h

---

## Pré-requisitos

- **Python 3.10+**
- **[Ollama](https://ollama.ai)** instalado e rodando com o modelo llama3:
  ```bash
  ollama pull llama3
  ollama serve
  ```
- **Credenciais Google** (Service Account com acesso às planilhas)
- **pip3** disponível no PATH

---

## Instalação — 5 etapas

**1. Clone ou copie o projeto:**
```bash
cd ~/luby-cashflow
```

**2. Instale as dependências:**
```bash
bash install.sh
```

**3. Configure as credenciais Google:**
```bash
mkdir -p ~/.config/luby-cashflow
cp /caminho/para/sua/service-account.json ~/.config/luby-cashflow/google_credentials.json
```

**4. Configure o `config/config.yaml`** (veja seção abaixo)

**5. Instale o cron:**
```bash
bash setup_cron.sh
```

---

## Configurando o config.yaml

Abra `config/config.yaml` e preencha:

```yaml
sheets:
  pipeline_br_id: "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms"   # ID da URL da planilha BR
  pipeline_br_aba: "Pipeline"                                         # Nome da aba
  pipeline_us_id: "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms"   # ID da planilha US
  pipeline_us_aba: "Pipeline"
  rp_bi_id: "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms"         # ID do RP/BI
  rp_bi_aba: "Projeção"

cambio:
  usd_brl_padrao: 5.10    # Fallback se a API de câmbio estiver fora

ollama:
  base_url: "http://localhost:11434"
  model: "llama3"
  timeout_segundos: 120
```

> O ID da planilha está na URL:  
> `https://docs.google.com/spreadsheets/d/**[ID AQUI]**/edit`

### Colunas esperadas nas planilhas

O sistema detecta colunas automaticamente por palavras-chave (case-insensitive):

| Planilha | Colunas obrigatórias | Colunas opcionais |
|---|---|---|
| Pipeline BR | `valor`, `data`/`mês` | `cliente`, `fase`, `categoria`, `bu` |
| Pipeline US | `amount`, `close date` | `account`, `stage`, `category` |
| RP/BI | `valor`, `competência` | `categoria`, `centro de custo`, `bu` |

---

## Drop do OMIE

Coloque os arquivos exportados do OMIE na pasta:

```
dados/omie_drop/
```

O sistema aceita:
- Arquivos `.csv` (separador `,` ou `;` detectado automaticamente)
- Arquivos `.xlsx`

Após processamento, os arquivos são renomeados com prefixo `processado_YYYY-MM-DD_` para evitar reprocessamento.

**Para contratos recorrentes mensais**, adicione uma coluna `recorrente` com valor `sim` — o sistema automaticamente expande em 12 entradas mensais.

---

## Execução manual

```bash
cd ~/luby-cashflow
python3 main.py
```

**Dry-run** (sem acessar fontes reais, usa dados mock):
```bash
python3 main.py --dry-run
```

---

## Instalando o cron (automático às 7h)

```bash
bash setup_cron.sh
```

Para verificar se instalou:
```bash
crontab -l
```

Para remover:
```bash
crontab -l | grep -v "luby-cashflow" | crontab -
```

---

## Onde ficam os relatórios

```
relatorios/
├── cashflow_2025-06-01.html   ← relatório visual (abra no navegador)
└── cashflow_2025-06-01.csv   ← dados numéricos por período
```

Os logs ficam em:
```
logs/cashflow.log
```

O histórico SQLite fica em:
```
dados/historico/cashflow.db
```

---

## Estrutura do projeto

```
luby-cashflow/
├── main.py              # Orquestrador — ponto de entrada
├── schema.py            # CashflowEntry e probabilidades de pipeline
├── db.py                # SQLite (salvar, consultar, deduplicar)
├── relatorio.py         # Gerador HTML + CSV
├── llama_client.py      # Cliente Ollama local
├── adaptadores/
│   ├── pipeline_br.py   # Google Sheets BR
│   ├── pipeline_us.py   # Google Sheets US (USD→BRL)
│   ├── omie.py          # Drop de arquivos OMIE
│   └── rp_bi.py         # RP/BI custos
├── config/config.yaml   # Configuração principal
├── install.sh           # Instalador de dependências
├── setup_cron.sh        # Instalador do cron
└── README.md
```

---

## Troubleshooting

| Problema | Solução |
|---|---|
| `gspread não instalado` | Execute `bash install.sh` |
| `Ollama não disponível` | Execute `ollama serve` antes de rodar |
| `Credenciais Google não encontradas` | Verifique `~/.config/luby-cashflow/google_credentials.json` |
| `ID da planilha não configurado` | Edite `config/config.yaml` |
| Planilha BR/US pulada | Configure os IDs no config.yaml e compartilhe a planilha com o service account |

---

*luby-cashflow v1.0.0 · Luby Tecnologia*
