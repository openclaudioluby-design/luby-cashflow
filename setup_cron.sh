#!/bin/bash
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
PYTHON=$(which python3)
CRON_JOB="0 7 * * * cd $SCRIPT_DIR && $PYTHON main.py >> logs/cashflow.log 2>&1  # luby-cashflow"

echo "Instalando cron job..."
echo "Job: $CRON_JOB"
echo ""

(crontab -l 2>/dev/null | grep -v "luby-cashflow"; echo "$CRON_JOB") | crontab -

echo "✅ Cron instalado com sucesso!"
echo ""
echo "Para verificar: crontab -l"
echo "Para remover:   crontab -l | grep -v 'luby-cashflow' | crontab -"
