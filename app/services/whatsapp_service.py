import json
import logging

from twilio.rest import Client
from config.settings import settings
from app.models.models import PlanoAlimentar

logger = logging.getLogger(__name__)

_client: Client | None = None

def get_client() -> Client:
    global _client
    if _client is None:
        _client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    return _client

def _fmt(phone: str) -> str:
    return phone if phone.startswith("whatsapp:") else f"whatsapp:{phone}"

async def send_message(to: str, message: str, *, force_freeform: bool = False) -> dict:
    """Envia mensagem no WhatsApp.

    Se TWILIO_CONTENT_SID estiver configurado, usa o template aprovado (Content API),
    que pode ser enviado a qualquer momento — inclusive fora da janela de 24h.
    A mensagem inteira vai na variável {{1}} do template.

    Sem o SID (ou com force_freeform), cai no envio freeform, que só é entregue
    dentro da janela de 24h após a última mensagem do usuário (erro 63016 fora dela).
    """
    params = {
        "from_": _fmt(settings.WHATSAPP_FROM),
        "to": _fmt(to),
    }
    usando_template = bool(settings.TWILIO_CONTENT_SID) and not force_freeform
    if usando_template:
        params["content_sid"] = settings.TWILIO_CONTENT_SID
        params["content_variables"] = json.dumps({"1": message})
    else:
        params["body"] = message

    msg = get_client().messages.create(**params)

    if not usando_template:
        logger.warning(
            "WhatsApp enviado em modo freeform (sem TWILIO_CONTENT_SID): "
            "só será entregue dentro da janela de 24h."
        )
    if getattr(msg, "error_code", None):
        logger.error("WhatsApp erro %s: %s", msg.error_code, msg.error_message)

    return {"sid": msg.sid, "status": msg.status, "error_code": getattr(msg, "error_code", None)}

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

_TREINO_LABELS = {
    "Z2_LONGO": "Z2 Longo", "TIROS": "Tiros", "VO2MAX": "VO2 Máx",
    "TEMPO": "Tempo", "FORCA": "Força", "RECUPERACAO": "Recuperação",
    "DESCANSO": "Descanso",
}


def format_semana_treinos_whatsapp(semana_inicio: str, treinos: list[dict]) -> str:
    """Resumo da semana de treinos para o WhatsApp (1 linha por dia)."""
    from datetime import datetime, timedelta
    dias = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    d0 = datetime.strptime(semana_inicio, "%Y-%m-%d").date()
    fim = d0 + timedelta(days=6)
    linhas = [f"🚴 *Treinos da semana — {d0.strftime('%d/%m')} a {fim.strftime('%d/%m')}*", ""]

    for t in sorted(treinos, key=lambda x: x.get("data", "")):
        try:
            dd = datetime.strptime(t["data"], "%Y-%m-%d").date()
            nome_dia, dstr = dias[dd.weekday()], dd.strftime("%d/%m")
        except Exception:
            nome_dia, dstr = "", t.get("data", "")
        tipo = t.get("tipo", "DESCANSO")
        if tipo == "DESCANSO" or not t.get("duracao_min"):
            linhas.append(f"*{nome_dia} {dstr}* — 🛌 Descanso")
            continue
        cab = f"*{nome_dia} {dstr}* — {_TREINO_LABELS.get(tipo, tipo)}"
        extras = []
        if t.get("duracao_min"):
            extras.append(f"⏱️ {t['duracao_min']} min")
        if t.get("cadencia_rpm"):
            extras.append(f"🔄 {t['cadencia_rpm']} rpm")
        if extras:
            cab += " · " + " · ".join(extras)
        linhas.append(cab)
        desc = (t.get("descricao") or "").strip()
        if desc:
            if len(desc) > 140:
                desc = desc[:137].rstrip() + "…"
            linhas.append(f"  _{desc}_")

    linhas += ["", "_MTB Nutrition Bot 🤖_"]
    return "\n".join(linhas)


async def send_semana_treinos(semana_inicio: str, treinos: list[dict]) -> dict:
    return await send_message(settings.WHATSAPP_TO,
                              format_semana_treinos_whatsapp(semana_inicio, treinos))


async def send_plano_diario(plano: PlanoAlimentar):
    return await send_message(settings.WHATSAPP_TO, format_plano_whatsapp(plano))

async def send_lembrete_refeicao(nome_refeicao: str, itens: list[str]):
    itens_str = "\n".join([f"  • {i}" for i in itens])
    mensagem  = f"⏰ *Hora da {nome_refeicao}!*\n\n{itens_str}\n\n_Bora manter o plano! 💪_"
    return await send_message(settings.WHATSAPP_TO, mensagem)
