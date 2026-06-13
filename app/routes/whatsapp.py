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


@router.post("/webhook")
async def whatsapp_webhook(request: Request):
    """Recebe mensagens de entrada do WhatsApp (Twilio). Se o usuário descrever
    ou fotografar algo que comeu fora do plano, registra a fuga de HOJE, reajusta
    o cardápio e responde com o plano atualizado."""
    form = await request.form()

    # 1) valida a assinatura da Twilio (segurança — o webhook é público)
    if settings.VALIDAR_TWILIO and settings.TWILIO_AUTH_TOKEN:
        try:
            from twilio.request_validator import RequestValidator
            validator = RequestValidator(settings.TWILIO_AUTH_TOKEN)
            assinatura = request.headers.get("X-Twilio-Signature", "")
            if not validator.validate(str(request.url), dict(form), assinatura):
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

    # 2) baixa a foto, se houver
    img_bytes = mime = None
    if num_media > 0 and form.get("MediaUrl0"):
        mime = form.get("MediaContentType0")
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as cli:
                r = await cli.get(form.get("MediaUrl0"),
                                  auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN))
                r.raise_for_status()
                img_bytes = r.content
        except Exception as e:
            logger.error("Webhook WhatsApp: falha ao baixar mídia: %s", e)

    if not body and not img_bytes:
        return _twiml("🍔 Me diga o que você comeu fora do plano (texto ou foto) "
                      "que eu ajusto teu cardápio de hoje.")

    # 3) estima as calorias com a IA
    from app.services.ai_service import estimar_alimento_extra, QuotaExcedida
    try:
        extra = await estimar_alimento_extra(body or None, img_bytes, mime)
    except QuotaExcedida:
        return _twiml("⚠️ A IA está sem cota agora. Tente mais tarde ou registre pelo portal.")
    except Exception as e:
        logger.error("Webhook WhatsApp: estimativa falhou: %s", e)
        return _twiml("Não consegui calcular as calorias disso. Tenta descrever de outro jeito?")

    if extra["kcal"] <= 0 and not img_bytes:
        return _twiml("Não entendi como comida. Ex.: '2 fatias de pizza' ou '1 pão de queijo'.")

    # 4) registra a fuga de hoje e reajusta o cardápio
    from app.services.config_service import adicionar_extra_dia, extras_do_dia, get_horarios
    from app.services.nutricao_service import plano_para_tipo, formatar_plano_whatsapp
    from app.routes.nutrition import _tipo_periodo_do_dia

    data = datetime.now().date().isoformat()
    await adicionar_extra_dia(data, extra)
    cfg = await get_horarios()
    tipo, periodo = await _tipo_periodo_do_dia(data)
    extras = await extras_do_dia(data)
    plano = plano_para_tipo(tipo, data, cfg, periodo=periodo, extras=extras)

    cabecalho = (f"🍔 Registrei: {extra['resumo']} (~{int(extra['kcal'])} kcal)\n"
                 f"Ajustei teu cardápio de hoje (cortei carbo) pra manter o total:\n\n")
    return _twiml(cabecalho + formatar_plano_whatsapp(data, plano))


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
