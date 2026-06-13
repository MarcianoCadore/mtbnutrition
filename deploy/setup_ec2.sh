#!/usr/bin/env bash
# Configura a EC2 (Ubuntu) para rodar o MTB Nutrition.
# Rode na instância DEPOIS de já ter copiado o código para /opt/mtbnutrition
# e criado o /opt/mtbnutrition/.env. Uso:  bash deploy/setup_ec2.sh
#
# Usa uv + Python 3.12 de propósito: o Ubuntu 26.04 vem com Python 3.14, que
# ainda não tem wheels p/ pydantic/etc e quebra a instalação. O uv baixa um
# Python 3.12 standalone (mesma linha do ambiente de dev) sem depender do apt.
set -euo pipefail

APP_DIR=/opt/mtbnutrition

echo ">> Instalando dependências do sistema..."
sudo apt-get update -y
command -v curl >/dev/null || sudo apt-get install -y curl

echo ">> Instalando uv (se necessário)..."
if ! command -v uv >/dev/null && [ ! -x "$HOME/.local/bin/uv" ]; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"

echo ">> Criando virtualenv (Python 3.12) e instalando requirements..."
cd "$APP_DIR"
if [ ! -d venv ]; then
  uv venv --python 3.12 venv
fi
uv pip install --python "$APP_DIR/venv/bin/python" -r requirements.txt

echo ">> Garantindo diretório de uploads persistente..."
mkdir -p "$APP_DIR/uploads/fit"

if [ ! -f "$APP_DIR/.env" ]; then
  echo "!! ERRO: $APP_DIR/.env não existe. Crie a partir do .env.example antes de continuar."
  exit 1
fi

echo ">> Instalando o serviço systemd..."
sudo cp deploy/mtbnutrition.service /etc/systemd/system/mtbnutrition.service
sudo systemctl daemon-reload
sudo systemctl enable mtbnutrition
sudo systemctl restart mtbnutrition

echo ">> Status:"
sleep 2
sudo systemctl --no-pager status mtbnutrition | head -15
echo
echo ">> Teste local:  curl -s http://127.0.0.1:8000/health"
curl -s http://127.0.0.1:8000/health && echo
echo ">> Pronto. Logs ao vivo:  sudo journalctl -u mtbnutrition -f"
