# 🚵 MTB Nutrition Bot

Plano alimentar inteligente para ciclistas MTB com notificações automáticas no WhatsApp.

## O que faz

- Gera cardápio diário personalizado via IA (Claude) baseado no treino do dia
- Envia plano completo no WhatsApp às 6h
- Lembretes automáticos: almoço (11h30), lanche (15h), janta (20h)
- Ajusta calorias e macros conforme tipo de treino (Z2, tiros, VO2max, descanso)
- Salva histórico no MongoDB

## Stack

- **Backend:** Python + FastAPI
- **IA:** Anthropic Claude (claude-sonnet-4)
- **WhatsApp:** Z-API
- **Banco:** MongoDB (Motor async)
- **Scheduler:** APScheduler
- **Deploy:** AWS EC2 Free Tier

## Setup local

### 1. Clonar e instalar dependências

```bash
cd mtb-nutrition-bot
python -m venv venv
source venv/bin/activate  # Mac/Linux
pip install -r requirements.txt
```

### 2. Configurar variáveis de ambiente

```bash
cp .env.example .env
# Editar .env com suas credenciais
```

### 3. Obter credenciais Z-API

1. Acessar https://z-api.io
2. Criar conta e instância
3. Conectar WhatsApp escaneando QR Code
4. Copiar Instance ID, Token e Client Token para o .env

### 4. Rodar localmente

```bash
uvicorn app.main:app --reload --port 8000
```

Acesse: http://localhost:8000/docs

## Endpoints principais

| Método | Rota | Descrição |
|--------|------|-----------|
| POST | /workout/ | Cadastrar treino do dia |
| GET | /workout/hoje | Ver treino de hoje |
| POST | /nutrition/gerar | Gerar plano alimentar |
| GET | /nutrition/hoje | Ver plano de hoje |
| POST | /whatsapp/teste | Testar envio WhatsApp |
| POST | /whatsapp/enviar-plano-agora | Enviar plano agora |

## Notificações automáticas

| Horário | Mensagem |
|---------|----------|
| 06:00 | Plano completo do dia |
| 11:30 | Lembrete almoço |
| 15:00 | Lembrete lanche |
| 20:00 | Lembrete janta |

## Deploy AWS EC2

```bash
# Na instância EC2 (Ubuntu)
sudo apt update && sudo apt install python3-pip python3-venv -y
git clone seu_repo
cd mtb-nutrition-bot
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env && nano .env

# Rodar em background
nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 &
```

## Zonas de FC (Marciano)

| Zona | Faixa | Tipo |
|------|-------|------|
| Z1 | até 134 bpm | Recuperação |
| Z2 | 135-153 bpm | Base aeróbica |
| Z3 | 154-164 bpm | Tempo |
| Z4 | 165-177 bpm | Limiar |
| Z5 | 178+ bpm | VO2max |
