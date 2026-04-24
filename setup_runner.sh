#!/bin/bash
# ============================================================
# setup_runner.sh — Instala o GitHub Actions self-hosted runner
# nesta máquina para o repo luby-cashflow
#
# Uso:
#   bash setup_runner.sh <GITHUB_REPO_URL> <RUNNER_TOKEN>
#
# Exemplo:
#   bash setup_runner.sh https://github.com/luby-openclaudio/luby-cashflow AAABxxxxxxx
#
# Para obter o RUNNER_TOKEN:
#   GitHub repo → Settings → Actions → Runners → "New self-hosted runner"
#   Copie o token da linha: --token XXXXX
# ============================================================

set -e

REPO_URL="${1:-}"
TOKEN="${2:-}"
RUNNER_DIR="$HOME/actions-runner"
RUNNER_VERSION="2.322.0"

if [[ -z "$REPO_URL" || -z "$TOKEN" ]]; then
  echo "Uso: bash setup_runner.sh <GITHUB_REPO_URL> <RUNNER_TOKEN>"
  echo ""
  echo "Obtenha o token em:"
  echo "  GitHub repo → Settings → Actions → Runners → New self-hosted runner"
  exit 1
fi

echo "=== Instalando GitHub Actions Runner ==="
echo "Repo: $REPO_URL"
echo ""

# Baixa runner para macOS ARM
mkdir -p "$RUNNER_DIR"
cd "$RUNNER_DIR"

RUNNER_PKG="actions-runner-osx-arm64-${RUNNER_VERSION}.tar.gz"
RUNNER_URL="https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${RUNNER_PKG}"

if [[ ! -f "$RUNNER_PKG" ]]; then
  echo "Baixando runner v${RUNNER_VERSION}..."
  curl -fsSL "$RUNNER_URL" -o "$RUNNER_PKG"
  tar xzf "$RUNNER_PKG"
fi

# Configura o runner
echo ""
echo "Configurando runner..."
./config.sh \
  --url "$REPO_URL" \
  --token "$TOKEN" \
  --name "mac-mini-luby" \
  --labels "self-hosted,macOS,arm64" \
  --work "$RUNNER_DIR/_work" \
  --unattended \
  --replace

# Instala como serviço LaunchAgent (inicia com login)
echo ""
echo "Instalando como serviço LaunchAgent..."
./svc.sh install
./svc.sh start

echo ""
echo "=== Runner instalado e rodando! ==="
echo ""
echo "Comandos úteis:"
echo "  Status:  cd $RUNNER_DIR && ./svc.sh status"
echo "  Parar:   cd $RUNNER_DIR && ./svc.sh stop"
echo "  Logs:    tail -f $RUNNER_DIR/_diag/*.log"
