#!/bin/bash
set -e
echo "=== Instalando luby-cashflow ==="
pip3 install gspread google-auth pandas openpyxl requests pyyaml

echo ""
echo "=== Criando pastas de dados ==="
mkdir -p dados/omie_drop dados/sheets_cache dados/historico relatorios logs

echo ""
echo "=== Instalação concluída! ==="
echo "Próximos passos:"
echo "  1. Configure config/config.yaml com os IDs das planilhas"
echo "  2. Coloque google_credentials.json em ~/.config/luby-cashflow/"
echo "  3. Certifique-se de que o Ollama está rodando: ollama serve"
echo "  4. Teste: python3 main.py --dry-run"
echo "  5. Instale o cron: bash setup_cron.sh"
