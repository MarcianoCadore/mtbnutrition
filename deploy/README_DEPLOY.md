# Deploy do MTB Nutrition na AWS (EC2 + MongoDB Atlas)

Arquitetura: **1 VM EC2 sempre ligada** rodando uvicorn + APScheduler (1 worker),
banco no **MongoDB Atlas** (free tier), portal protegido por **login HTTP Basic**.

---

## Fase 3 — MongoDB Atlas (banco grátis)

1. Crie conta em https://www.mongodb.com/cloud/atlas → **Build a Database** → plano **M0 (Free)**.
2. Região: escolha a mais perto da EC2 (ex.: `sa-east-1` São Paulo).
3. **Database Access** → crie um usuário (ex.: `mtbapp`) com senha forte. Guarde a senha.
4. **Network Access** → Add IP Address → por enquanto `0.0.0.0/0` (libera geral).
   Depois troque pelo IP fixo da EC2 (Fase 4) para fechar.
5. **Connect → Drivers** → copie a connection string. Fica assim:
   `mongodb+srv://mtbapp:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority`
   Troque `<password>` pela senha real. Essa string vai no `.env` como `MONGODB_URL`.

## Fase 3.1 — Migrar os dados locais para o Atlas

Com o Mongo local no ar, rode na sua máquina:

```bash
cd ~/projetoiaperformancenutri
SOURCE_URL="mongodb://127.0.0.1:27017" \
DEST_URL="mongodb+srv://mtbapp:SUA_SENHA@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority" \
./venv/bin/python -m scripts.migrar_para_atlas
```

---

## Fase 4 — Criar a EC2

1. Console AWS → **EC2 → Launch instance**.
   - Name: `mtbnutrition`
   - AMI: **Ubuntu Server 24.04 LTS**
   - Tipo: **t3.micro** (free tier 12 meses)
   - Key pair: crie uma nova (ex.: `mtb-key`) e **baixe o .pem** (guarde bem).
   - Network → **Security group**, libere as portas:
     - SSH (22) → **My IP** (só seu IP)
     - HTTP (80) → Anywhere  *(se for usar HTTPS/Caddy)*
     - Custom TCP **8000** → Anywhere  *(acesso direto ao app, modo simples)*
2. Launch. Anote o **Public IPv4** (ex.: `18.230.x.x`).
3. (Recomendado) **Elastic IP**: EC2 → Elastic IPs → Allocate → Associate à instância,
   pra o IP não mudar quando reiniciar.

## Fase 5 — Enviar o código e subir

Na **sua máquina** (ajuste o IP e o caminho do .pem):

```bash
cd ~/projetoiaperformancenutri
chmod 400 ~/Downloads/mtb-key.pem
EC2=ubuntu@18.230.x.x
PEM=~/Downloads/mtb-key.pem

# 1) cria a pasta no servidor
ssh -i $PEM $EC2 "sudo mkdir -p /opt/mtbnutrition && sudo chown ubuntu:ubuntu /opt/mtbnutrition"

# 2) copia o código (sem venv, .git, uploads, .env, .claude)
rsync -avz -e "ssh -i $PEM" \
  --exclude venv --exclude .git --exclude '__pycache__' \
  --exclude uploads --exclude .env --exclude .claude \
  ./ $EC2:/opt/mtbnutrition/
```

Agora crie o `.env` no servidor:

```bash
ssh -i $PEM $EC2
# já dentro da EC2:
cd /opt/mtbnutrition
cp .env.example .env
nano .env      # preencha MONGODB_URL (Atlas), PORTAL_PASSWORD, GEMINI, Twilio, Garmin
```

Rode o setup (instala deps + serviço systemd + sobe):

```bash
bash deploy/setup_ec2.sh
```

Pronto. Acesse no navegador: `http://18.230.x.x:8000` → vai pedir usuário/senha (PORTAL_USER/PORTAL_PASSWORD).

Comandos úteis na EC2:
```bash
sudo systemctl status mtbnutrition      # estado
sudo journalctl -u mtbnutrition -f      # logs ao vivo
sudo systemctl restart mtbnutrition     # reiniciar
```

Para **atualizar** depois de mudar código (na sua máquina):
```bash
rsync -avz -e "ssh -i $PEM" --exclude venv --exclude .git --exclude '__pycache__' \
  --exclude uploads --exclude .env --exclude .claude ./ $EC2:/opt/mtbnutrition/
ssh -i $PEM $EC2 "cd /opt/mtbnutrition && ./venv/bin/pip install -r requirements.txt && sudo systemctl restart mtbnutrition"
```

---

## Opcional (recomendado) — HTTPS com domínio + Caddy

O login Basic em HTTP puro trafega a senha em base64 (não criptografada). Com um domínio
você ganha HTTPS automático e grátis. Aponte um registro A do domínio para o IP da EC2 e:

```bash
sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt-get update && sudo apt-get install -y caddy
```

`/etc/caddy/Caddyfile`:
```
seu-dominio.com {
    reverse_proxy 127.0.0.1:8000
}
```
```bash
sudo systemctl restart caddy
```

Depois feche a porta 8000 no Security Group (deixe só 80/443) e o acesso passa a ser
`https://seu-dominio.com`.
