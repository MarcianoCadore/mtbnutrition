import logging
from xml.sax.saxutils import escape

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel
from datetime import datetime
from app.services.whatsapp_service import send_message, send_plano_diario
from app.services.mongo_service import get_db
from app.models.models import PlanoAlimentar
from config.settings import settings

router = APIRouter()
logger = logging.getLogger(__name__)


def _twiml(mensagem: str) -> Response:
    """Resposta TwiML que faz o WhatsApp responder com 'mensagem'."""
    xml = (f'<?xml version="1.0" encoding="UTF-8"?>'
           f'<Response><Message>{escape(mensagem)}</Message></Response>')
    return Response(content=xml, media_type="application/xml")


def _ref_datas() -> str:
    """Texto com as datas de referência (hoje/amanhã/ontem + dias da semana atual)
    para a IA resolver expressões como 'quinta' ou 'amanhã'."""
    from datetime import date, timedelta
    nomes = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
    hoje = date.today()
    seg = hoje - timedelta(days=hoje.weekday())
    linhas = [f"hoje = {hoje.isoformat()} ({nomes[hoje.weekday()]}-feira)",
              f"amanhã = {(hoje + timedelta(days=1)).isoformat()}",
              f"ontem = {(hoje - timedelta(days=1)).isoformat()}"]
    for i, nm in enumerate(nomes):
        linhas.append(f"{nm} desta semana = {(seg + timedelta(days=i)).isoformat()}")
    return "\n".join(linhas)


async def _plano_do_dia_msg(data: str) -> str:
    from app.services.config_service import get_horarios, extras_do_dia
    from app.services.nutricao_service import plano_para_tipo, formatar_plano_whatsapp
    from app.routes.nutrition import _tipo_periodo_do_dia
    cfg = await get_horarios()
    tipo, periodo = await _tipo_periodo_do_dia(data)
    extras = await extras_do_dia(data)
    plano = plano_para_tipo(tipo, data, cfg, periodo=periodo, extras=extras)
    return formatar_plano_whatsapp(data, plano)


async def _treino_do_dia_msg(data: str) -> str:
    from datetime import datetime, timedelta
    d = datetime.fromisoformat(data).date()
    seg = d - timedelta(days=d.weekday())
    dias = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    cab = f"🚴 *Treino de {dias[d.weekday()]}, {d.strftime('%d/%m')}*"
    doc = await get_db().semanas.find_one({"semana_inicio": seg.isoformat()})
    if doc:
        for t in doc.get("treinos", []):
            if t.get("data") == data:
                tipo = t.get("tipo") or "DESCANSO"
                if tipo == "DESCANSO":
                    return cab + "\n🛌 Descanso — sem treino."
                partes = [cab, f"Tipo: {tipo.replace('_', ' ').title()}"]
                if t.get("duracao_min"):  partes.append(f"⏱️ {t['duracao_min']} min")
                if t.get("distancia_km"): partes.append(f"📏 {t['distancia_km']} km")
                if t.get("cadencia_rpm"): partes.append(f"🔄 {t['cadencia_rpm']} rpm")
                if t.get("descricao"):    partes.append(f"📝 {t['descricao']}")
                return "\n".join(partes)
    return cab + "\n🛌 Sem treino marcado (descanso)."


async def _registrar_fuga_msg(extra: dict, data: str) -> str:
    from app.services.config_service import adicionar_extra_dia
    await adicionar_extra_dia(data, extra)
    return (f"🍔 Registrei: {extra['resumo']} (~{int(extra['kcal'])} kcal)\n"
            f"Ajustei o cardápio (cortei carbo) pra manter o total:\n\n"
            f"{await _plano_do_dia_msg(data)}")


@router.post("/webhook")
async def whatsapp_webhook(request: Request):
    """Assistente de WhatsApp: entende a intenção (cardápio/treino de um dia,
    registrar fuga por texto ou foto, trocar alimento, conversar) e responde."""
    from datetime import datetime
    form = await request.form()

    # validação de assinatura da Twilio (o webhook é público)
    if settings.VALIDAR_TWILIO and settings.TWILIO_AUTH_TOKEN:
        try:
            from twilio.request_validator import RequestValidator
            validator = RequestValidator(settings.TWILIO_AUTH_TOKEN)
            if not validator.validate(str(request.url), dict(form), request.headers.get("X-Twilio-Signature", "")):
                logger.warning("Webhook WhatsApp: assinatura Twilio inválida (url=%s)", request.url)
                return Response(status_code=403, content="assinatura inválida")
        except Exception as e:
            logger.error("Webhook WhatsApp: erro na validação: %s", e)
            return Response(status_code=403, content="erro de validação")

    body = (form.get("Body") or "").strip()
    try:
        num_media = int(form.get("NumMedia") or 0)
    except ValueError:
        num_media = 0
    hoje = datetime.now().date().isoformat()

    from app.services.ai_service import estimar_alimento_extra, interpretar_mensagem, QuotaExcedida

    # FOTO → sempre tratada como fuga (comida fotografada), no dia de hoje
    if num_media > 0 and form.get("MediaUrl0"):
        img_bytes = None
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as cli:
                r = await cli.get(form.get("MediaUrl0"),
                                  auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN))
                r.raise_for_status()
                img_bytes = r.content
        except Exception as e:
            logger.error("Webhook WhatsApp: falha ao baixar mídia: %s", e)
            return _twiml("Não consegui abrir a foto. Tenta de novo ou descreve por texto.")
        try:
            extra = await estimar_alimento_extra(body or None, img_bytes, form.get("MediaContentType0"))
        except QuotaExcedida:
            return _twiml("⚠️ A IA está sem cota agora. Tenta mais tarde ou registra pelo portal.")
        except Exception as e:
            logger.error("Webhook foto: %s", e)
            return _twiml("Não consegui calcular as calorias da foto. Descreve o que era?")
        return _twiml(await _registrar_fuga_msg(extra, hoje))

    if not body:
        return _twiml("🚴 Oi! Sou teu assistente. Posso te dizer o *cardápio* ou o *treino* de um dia, "
                      "registrar o que você *comeu fora do plano* (texto ou foto) e trocar alimentos. Manda aí!")

    # TEXTO → classifica a intenção
    try:
        interp = await interpretar_mensagem(body, _ref_datas())
    except QuotaExcedida:
        return _twiml("⚠️ A IA está sem cota agora. Tenta de novo mais tarde.")
    except Exception as e:
        logger.error("Webhook interpretar: %s", e)
        return _twiml("Não entendi bem 🤔 Ex.: 'cardápio de hoje', 'treino de quinta', 'comi um pão de queijo'.")

    intencao = interp.get("intencao", "conversa")
    # a IA às vezes devolve a data como o texto "null" ou em formato inválido
    data = interp.get("data")
    if not data or str(data).lower() == "null":
        data = hoje
    else:
        try:
            datetime.fromisoformat(data)
        except (ValueError, TypeError):
            data = hoje

    if intencao == "plano_dia":
        return _twiml(await _plano_do_dia_msg(data))
    if intencao == "treino_dia":
        return _twiml(await _treino_do_dia_msg(data))
    if intencao in ("registrar_fuga", "trocar_alimento"):
        desc = (interp.get("para") if intencao == "trocar_alimento" else interp.get("descricao")) or body
        try:
            extra = await estimar_alimento_extra(desc, None, None)
        except QuotaExcedida:
            return _twiml("⚠️ A IA está sem cota agora. Tenta mais tarde.")
        except Exception as e:
            logger.error("Webhook fuga texto: %s", e)
            return _twiml("Não consegui calcular as calorias disso. Tenta descrever de outro jeito?")
        msg = await _registrar_fuga_msg(extra, data)
        if intencao == "trocar_alimento" and interp.get("de"):
            msg = f"🔁 Beleza, pode trocar *{interp['de']}* por *{interp['para']}*.\n" + msg
        return _twiml(msg)

    # conversa geral
    return _twiml(interp.get("resposta") or
                  "🚴 Posso te dizer o cardápio ou o treino de um dia, registrar o que comeu fora do plano "
                  "(texto/foto) e trocar alimentos. É só falar!")


class MensagemBody(BaseModel):
    mensagem: str


@router.get("/", response_class=HTMLResponse)
async def ui_enviar_mensagem():
    return """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>MTB Nutrition — WhatsApp</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #f0f2f5; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
    .card { background: white; border-radius: 14px; padding: 36px; width: 100%; max-width: 500px; box-shadow: 0 4px 20px rgba(0,0,0,0.1); }
    .logo { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
    .logo h1 { color: #128c7e; font-size: 1.4rem; }
    p.sub { color: #888; font-size: 0.88rem; margin-bottom: 24px; }
    label { display: block; font-size: 0.85rem; font-weight: 600; color: #444; margin-bottom: 6px; }
    textarea { width: 100%; border: 1.5px solid #ddd; border-radius: 10px; padding: 12px; font-size: 1rem; resize: vertical; min-height: 150px; outline: none; font-family: inherit; transition: border-color 0.2s; line-height: 1.5; }
    textarea:focus { border-color: #128c7e; }
    .count { text-align: right; color: #bbb; font-size: 0.78rem; margin: 5px 0 20px; }
    button { width: 100%; padding: 14px; background: #128c7e; color: white; border: none; border-radius: 10px; font-size: 1rem; font-weight: 700; cursor: pointer; transition: background 0.2s; letter-spacing: 0.3px; }
    button:hover:not(:disabled) { background: #0a7163; }
    button:disabled { background: #b2dfdb; cursor: not-allowed; }
    .status { margin-top: 16px; padding: 12px 16px; border-radius: 10px; font-size: 0.9rem; display: none; }
    .ok  { background: #e8f5e9; color: #2e7d32; display: block; }
    .err { background: #fdecea; color: #c62828; display: block; }
  </style>
</head>
<body>
<div class="card">
  <div class="logo"><span style="font-size:1.8rem">🚵</span><h1>MTB Nutrition</h1></div>
  <p class="sub">Enviar mensagem manual via WhatsApp</p>
  <label for="msg">Mensagem</label>
  <textarea id="msg" placeholder="Digite sua mensagem aqui..." oninput="cnt()"></textarea>
  <div class="count"><span id="n">0</span> caracteres</div>
  <button id="btn" onclick="send()">📤 Enviar</button>
  <div id="st" class="status"></div>
</div>
<script>
  function cnt() { document.getElementById('n').textContent = document.getElementById('msg').value.length; }
  async function send() {
    const msg = document.getElementById('msg').value.trim();
    const btn = document.getElementById('btn');
    const st  = document.getElementById('st');
    if (!msg) { st.className='status err'; st.textContent='⚠️ Digite uma mensagem antes de enviar.'; return; }
    btn.disabled = true; btn.textContent = 'Enviando...';
    st.className = 'status'; st.textContent = '';
    try {
      const r = await fetch('/whatsapp/mensagem', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({mensagem: msg}) });
      const d = await r.json();
      if (r.ok) { st.className='status ok'; st.textContent='✅ Mensagem enviada com sucesso!'; document.getElementById('msg').value=''; cnt(); }
      else { throw new Error(d.detail || JSON.stringify(d)); }
    } catch(e) { st.className='status err'; st.textContent='❌ Erro: ' + e.message; }
    finally { btn.disabled=false; btn.textContent='📤 Enviar'; }
  }
  document.getElementById('msg').addEventListener('keydown', e => { if (e.ctrlKey && e.key === 'Enter') send(); });
</script>
</body>
</html>"""


@router.post("/mensagem")
async def enviar_mensagem(body: MensagemBody):
    mensagem = body.mensagem.strip()
    if not mensagem:
        raise HTTPException(status_code=400, detail="Mensagem não pode ser vazia")
    if not settings.WHATSAPP_TO:
        raise HTTPException(status_code=500, detail="Configure WHATSAPP_TO no .env")
    result = await send_message(settings.WHATSAPP_TO, mensagem)
    return {"status": "enviado", "result": result}


@router.post("/teste")
async def testar_whatsapp():
    if not settings.WHATSAPP_TO:
        raise HTTPException(status_code=500, detail="Configure WHATSAPP_TO no .env")
    result = await send_message(settings.WHATSAPP_TO, "✅ *MTB Nutrition Bot* — teste de conexão bem-sucedido! 🚵")
    return {"status": "enviado", "result": result}


@router.post("/send-plano")
async def enviar_plano_hoje():
    db = get_db()
    hoje = datetime.now().date()
    doc = await db.planos.find_one(
        {"data": {"$gte": datetime(hoje.year, hoje.month, hoje.day)}},
        {"_id": 0}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Nenhum plano para hoje")
    plano = PlanoAlimentar(**doc)
    result = await send_plano_diario(plano)
    return {"status": "enviado", "result": result}
