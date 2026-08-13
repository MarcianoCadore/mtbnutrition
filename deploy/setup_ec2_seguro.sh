#!/usr/bin/env bash
# ==========================================================================
# Provisiona o MTB Nutrition na EC2 NOVA, endurecido.
#
# Complementa o deploy/setup_ec2_seguro.sh do Pedal da Laranja, que prepara a
# base do host (Node, swap, Caddy, atualizações automáticas). Rode aquele
# primeiro; este cuida só do FastAPI.
#
# Contexto: na invasão de 12/08/2026 os dois sites dividiam a mesma EC2 e o
# invasor virou root pelo sudo sem senha do usuário ubuntu — que era quem
# rodava as duas aplicações. Aqui o app passa a rodar como `mtbnutri`, sem sudo.
#
# Uso (dentro da instância nova, como ubuntu):
#   bash deploy/setup_ec2_seguro.sh
# ==========================================================================
set -euo pipefail

APP_DIR=/opt/mtbnutrition
APP_USER=mtbnutri

echo "==> 1/6  Python e ferramentas de build"
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  python3 python3-venv python3-dev build-essential >/dev/null
python3 --version

echo "==> 2/6  Usuário de serviço sem privilégios"
if ! id "$APP_USER" >/dev/null 2>&1; then
  sudo useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
fi
sudo mkdir -p "$APP_DIR/uploads"
sudo chown -R "$APP_USER:$APP_USER" "$APP_DIR"
sudo usermod -aG "$APP_USER" ubuntu || true

echo "==> 3/6  Ambiente virtual e dependências"
cd "$APP_DIR"
if [[ ! -f .env ]]; then
  echo "!! FALTA o arquivo ${APP_DIR}/.env — crie-o antes de seguir."
  exit 1
fi
sudo chown "$APP_USER:$APP_USER" .env
sudo chmod 600 .env
sudo -u "$APP_USER" python3 -m venv "$APP_DIR/venv"
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install --quiet --upgrade pip
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install --quiet -r requirements.txt
sudo chown -R "$APP_USER:$APP_USER" "$APP_DIR"

echo "==> 4/6  Serviço systemd endurecido"
sudo tee /etc/systemd/system/mtbnutrition.service >/dev/null <<UNIT
[Unit]
Description=MTB Nutrition (FastAPI + APScheduler)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
Environment=HOME=${APP_DIR}
# IMPORTANTE: 1 worker só — o APScheduler roda dentro do processo e não pode
# ser duplicado (senão os jobs/WhatsApp disparam em dobro).
# Escuta só no loopback: quem atende de fora é o Caddy.
ExecStart=${APP_DIR}/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=always
RestartSec=5

# --- Contenção: sem escalada de privilégio ---
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
ProtectClock=true
RestrictSUIDSGID=true
RestrictNamespaces=true
RestrictRealtime=true
LockPersonality=true
# AF_NETLINK é necessário para enumerar interfaces de rede (os/psutil/uvicorn).
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX AF_NETLINK
ReadWritePaths=${APP_DIR}/uploads

# --- Teto de memória: minerador morre aqui dentro, não derruba o Caddy ---
MemoryMax=700M
MemoryHigh=600M
TasksMax=150

[Install]
WantedBy=multi-user.target
UNIT

echo "==> 5/6  Subindo"
sudo systemctl daemon-reload
sudo systemctl enable --now mtbnutrition
sudo systemctl restart mtbnutrition

echo "==> 6/6  Verificação"
sleep 8
systemctl is-active mtbnutrition
curl -s -o /dev/null -w "127.0.0.1:8000 -> HTTP %{http_code}\n" --max-time 20 http://127.0.0.1:8000/
echo "-- o app NÃO pode ter sudo (deve falhar) --"
if sudo -u "$APP_USER" sudo -n true 2>/dev/null; then
  echo "   FALHA: usuário do app conseguiu sudo!"
  exit 1
else
  echo "   OK: usuário do app não consegue escalar privilégio."
fi
