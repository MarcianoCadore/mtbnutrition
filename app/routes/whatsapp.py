from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from datetime import datetime
from app.services.whatsapp_service import send_message, send_plano_diario
from app.services.mongo_service import get_db
from app.models.models import PlanoAlimentar
from config.settings import settings

router = APIRouter()


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
