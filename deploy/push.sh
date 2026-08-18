#!/usr/bin/env bash
# Deploy do mtbnutrition para a VM (rsync -> pip install -> restart).
# Comando único (para ser aprovado automaticamente pela allowlist do Claude).
#
# Migrado da AWS para a Magalu Cloud em 17-18/08/2026: a EC2 compartilhada com
# o Pedal (18.230.117.0) ficou totalmente inacessível pela rede (não só o app
# — nem SSH nem ping respondiam) e o usuário optou por não depender mais da
# AWS. VM dedicada: mtbnutrition (BV1-1-10, br-se1-a).
# /opt/mtbnutrition pertence ao usuário de serviço `mtbnutri`, que não tem
# sudo — daí o --rsync-path com sudo, e o chown depois da cópia.
set -euo pipefail
cd "$(dirname "$0")/.."

EC2=ubuntu@201.54.19.234
PEM=~/.ssh/id_ed25519
APP=/opt/mtbnutrition

echo ">> rsync do código"
rsync -az --delete -e "ssh -i $PEM -o BatchMode=yes" --rsync-path="sudo rsync" \
  --exclude venv --exclude .git --exclude __pycache__ --exclude .pytest_cache \
  --exclude uploads --exclude .env --exclude '.env.bak-*' --exclude .coverage \
  --exclude '*.pyc' --exclude .garth_mtb \
  ./ "$EC2:$APP/"

echo ">> dependências + restart remoto"
ssh -i "$PEM" -o BatchMode=yes -o ServerAliveInterval=30 "$EC2" "
  sudo chown -R mtbnutri:mtbnutri $APP
  cd $APP && sudo -u mtbnutri $APP/venv/bin/pip install --quiet -r requirements.txt || { echo FALHOU; exit 1; }
  sudo chown -R mtbnutri:mtbnutri $APP
  sudo systemctl restart mtbnutrition
"

echo ">> conferindo"
for i in $(seq 1 20); do
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 https://mtbnutrition.com.br/ || true)
  [ "$code" = "200" ] && { echo "DEPLOY_OK (HTTP 200)"; exit 0; }
  sleep 5
done
echo "ATENÇÃO: o site não respondeu 200 depois do deploy."
exit 1
