from twilio.rest import Client
from config.settings import settings
from app.models.models import PlanoAlimentar

_client: Client | None = None

def get_client() -> Client:
    global _client
    if _client is None:
        _client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    return _client

def _fmt(phone: str) -> str:
    return phone if phone.startswith("whatsapp:") else f"whatsapp:{phone}"

async def send_message(to: str, message: str) -> dict:
    msg = get_client().messages.create(
        from_=_fmt(settings.WHATSAPP_FROM),
        to=_fmt(to),
        body=message,
    )
    return {"sid": msg.sid, "status": msg.status}

def format_plano_whatsapp(plano: PlanoAlimentar) -> str:
    data_str   = plano.data.strftime("%d/%m/%Y")
    dia_semana = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    dia = dia_semana[plano.data.weekday()]

    linhas = [
        f"🚵 *MTB Nutrition — {dia}, {data_str}*",
        f"📊 Tipo: {plano.tipo_dia.replace('_', ' ').title()}",
        f"🔥 Meta: {plano.kcal_total} kcal | 💪 Proteína: {plano.proteina_total_g}g",
        ""
    ]

    if plano.treino:
        linhas += [f"🏋️ *Treino:* {plano.treino.tipo} — {plano.treino.duracao_min} min", ""]

    linhas.append("🍽️ *Cardápio do dia:*")
    linhas.append("")

    for r in plano.refeicoes:
        linhas.append(f"*{r.horario} — {r.nome}*")
        for item in r.itens:
            linhas.append(f"  • {item}")
        linhas.append(f"  _{r.kcal_estimado} kcal | {r.proteina_g}g prot_")
        if r.observacao:
            linhas.append(f"  ⚠️ {r.observacao}")
        linhas.append("")

    linhas.append("💧 Hidratação mínima: 3L de água")
    linhas.append("_Gerado pelo MTB Nutrition Bot 🤖_")

    return "\n".join(linhas)

async def send_plano_diario(plano: PlanoAlimentar):
    return await send_message(settings.WHATSAPP_TO, format_plano_whatsapp(plano))

async def send_lembrete_refeicao(nome_refeicao: str, itens: list[str]):
    itens_str = "\n".join([f"  • {i}" for i in itens])
    mensagem  = f"⏰ *Hora da {nome_refeicao}!*\n\n{itens_str}\n\n_Bora manter o plano! 💪_"
    return await send_message(settings.WHATSAPP_TO, mensagem)
