"""Tela de assinatura: Pix, comprovante no WhatsApp e status do trial.

Fica atrás do login (precisa saber quem é para mostrar o estado certo), mas é
liberada pelo gate de assinatura — senão quem venceu não conseguiria chegar na
tela que resolve o vencimento.
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app import pix
from app.services import assinatura_service, user_service

router = APIRouter()

WHATSAPP_SUPORTE = "5554999441016"
WHATSAPP_SUPORTE_LABEL = "(54) 99944-1016"

_HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Assinatura — MTB Nutrition</title>
  <style>
    :root { --green:#128c7e; --whats:#25d366; --bg:#f0f2f5; --card:#fff; --text:#1a1a2e; --muted:#6b7280; --border:#e0e0e0; }
    * { box-sizing:border-box; margin:0; padding:0; }
    body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; background:var(--bg); color:var(--text); min-height:100vh; display:flex; align-items:center; justify-content:center; padding:20px; }
    .card { background:var(--card); border-radius:16px; box-shadow:0 6px 30px rgba(0,0,0,.12); width:100%; max-width:460px; overflow:hidden; }
    .card-head { background:var(--green); color:#fff; padding:24px; text-align:center; }
    .card-head .logo { font-size:1.25rem; font-weight:700; }
    .card-head .sub { font-size:.84rem; opacity:.9; margin-top:5px; line-height:1.45; }
    .card-body { padding:24px; }
    .status { border-radius:10px; padding:12px 14px; font-size:.88rem; font-weight:600; margin-bottom:18px; line-height:1.5; }
    .status.trial { background:#e8f5e9; color:#1b5e20; }
    .status.venceu { background:#fdecea; color:#c62828; }
    .status.ativa { background:#e3f2fd; color:#0d47a1; }
    .step { display:flex; align-items:flex-start; gap:10px; margin-bottom:14px; }
    .step-num { display:flex; align-items:center; justify-content:center; width:22px; height:22px; border-radius:50%; background:var(--green); color:#fff; font-size:.75rem; font-weight:700; flex-shrink:0; }
    .step p { font-size:.9rem; color:#333; line-height:1.5; }
    .qr-wrap { text-align:center; margin:4px 0 18px; }
    .qr-wrap svg { max-width:210px; width:100%; height:auto; border:1px solid var(--border); border-radius:10px; padding:10px; background:#fff; }
    .qr-valor { font-weight:700; margin-top:8px; font-size:.95rem; }
    .qr-ciclo { font-size:.78rem; color:var(--muted); margin-top:2px; }
    .pix-row { display:flex; gap:8px; margin-bottom:18px; }
    .pix-code { flex:1; border:1.5px solid var(--border); border-radius:8px; padding:10px 12px; font-size:.7rem; font-family:monospace; color:var(--muted); background:#fafafa; resize:none; }
    .copy-btn { border:1.5px solid var(--green); background:#fff; color:var(--green); border-radius:8px; padding:0 14px; font-size:.82rem; font-weight:700; cursor:pointer; white-space:nowrap; }
    .copy-btn:hover { background:var(--green); color:#fff; }
    .whats-btn { display:flex; align-items:center; justify-content:center; gap:8px; width:100%; background:var(--whats); color:#fff; border:none; border-radius:10px; padding:14px; font-size:.95rem; font-weight:700; text-decoration:none; margin-bottom:14px; }
    .whats-btn:hover { background:#1ebc59; }
    .final-note { font-size:.8rem; color:var(--muted); text-align:center; line-height:1.55; }
    .links { text-align:center; margin-top:18px; font-size:.8rem; }
    .links a { color:var(--muted); text-decoration:none; margin:0 7px; }
    .links a:hover { color:var(--green); text-decoration:underline; }
  </style>
</head>
<body>
<div class="card">
  <div class="card-head">
    <div class="logo">🚵 MTB Nutrition</div>
    <div class="sub">{{SUBTITULO}}</div>
  </div>
  <div class="card-body">
    {{STATUS}}
    <div class="step">
      <span class="step-num">1</span>
      <p>Pague com o QR code Pix abaixo — ou copie o código e cole no seu banco.</p>
    </div>
    <div class="qr-wrap">
      {{QRCODE_SVG}}
      <div class="qr-valor">R$ 24,99 · Plano Atleta</div>
      <div class="qr-ciclo">Acesso liberado por 30 dias a cada pagamento. Sem cartão salvo, sem cobrança automática.</div>
    </div>
    <div class="pix-row">
      <textarea class="pix-code" id="pixCode" readonly rows="3">{{PIX_PAYLOAD}}</textarea>
      <button class="copy-btn" type="button" onclick="copiarPix()">Copiar</button>
    </div>
    <div class="step">
      <span class="step-num">2</span>
      <p>Mande o comprovante no WhatsApp <b>{{WHATSAPP_LABEL}}</b>. Conferimos e liberamos seu acesso — normalmente no mesmo dia.</p>
    </div>
    <a class="whats-btn" href="https://wa.me/{{WHATSAPP}}?text={{WHATSAPP_TEXTO}}" target="_blank" rel="noopener">
      💬 Enviar comprovante no WhatsApp
    </a>
    <p class="final-note">{{RODAPE}}</p>
    <div class="links">
      <a href="/portal/">Voltar ao portal</a>·<a href="/termos">Termos de uso</a>·<a href="/privacidade">Privacidade</a>·<a href="/logout">Sair</a>
    </div>
  </div>
</div>
<script>
function copiarPix(){
  var el = document.getElementById('pixCode');
  el.select();
  el.setSelectionRange(0, 99999);
  if (navigator.clipboard) {
    navigator.clipboard.writeText(el.value).catch(function(){ document.execCommand('copy'); });
  } else {
    document.execCommand('copy');
  }
}
</script>
</body>
</html>"""


def _plural(n: int, sing: str, plur: str) -> str:
    return sing if n == 1 else plur


def _bloco_status(est: dict, nome: str) -> tuple[str, str, str]:
    """(subtítulo do cabeçalho, caixa de status, rodapé) conforme o estado."""
    dias = est.get("dias")
    primeiro = (nome or "").split(" ")[0]

    if est["status"] == "trial":
        d = dias or 0
        sub = f"Seu teste grátis termina em {d} {_plural(d, 'dia', 'dias')}"
        status = (f"<div class='status trial'>✅ Você está no teste grátis — "
                  f"faltam <b>{d} {_plural(d, 'dia', 'dias')}</b>. "
                  "Pode assinar agora: os dias que sobraram do teste são somados "
                  "ao seu primeiro mês, você não perde nada por pagar antes.</div>")
        rodape = ("Não quer assinar agora? É só fechar esta tela e continuar usando "
                  "até o fim do teste.")
        return sub, status, rodape

    if est["status"] == "ativa":
        ate = est.get("pago_ate")
        quando = ate.strftime("%d/%m/%Y") if ate else "—"
        sub = "Assinatura ativa"
        status = (f"<div class='status ativa'>💚 Assinatura ativa até <b>{quando}</b>. "
                  "Pode renovar antes do vencimento — o novo pagamento soma 30 dias "
                  "ao que você já tem.</div>")
        return sub, status, "Obrigado por apoiar o projeto."

    if est["status"] == "cancelada":
        sub = "Assinatura cancelada"
        status = ("<div class='status venceu'>Sua assinatura foi cancelada. "
                  "Para voltar, pague o Pix abaixo e mande o comprovante.</div>")
    else:
        sub = "Seu acesso venceu"
        status = ("<div class='status venceu'>⏳ Seu período de acesso terminou. "
                  "Seus treinos, análises e histórico continuam salvos — e voltam "
                  "no mesmo lugar assim que o pagamento for confirmado.</div>")

    rodape = (f"{primeiro}, seu histórico não é apagado. " if primeiro else "Seu histórico não é apagado. ")
    rodape += "Você ainda consegue consultar o que já treinou pelo portal."
    return sub, status, rodape


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def pagina_assinatura(request: Request):
    user_id = getattr(request.state, "user_id", None)
    u = await user_service.get_por_id(user_id) if user_id else None
    est = assinatura_service.estado(u)

    sub, status, rodape = _bloco_status(est, (u or {}).get("nome", ""))
    texto = "Ola!+Segue+o+comprovante+de+pagamento+-+MTB+Nutrition"
    login = (u or {}).get("login")
    if login:
        texto += f"+-+usuario+{login}"

    html = (_HTML
            .replace("{{SUBTITULO}}", sub)
            .replace("{{STATUS}}", status)
            .replace("{{RODAPE}}", rodape)
            .replace("{{QRCODE_SVG}}", pix.get_qrcode_svg())
            .replace("{{PIX_PAYLOAD}}", pix.PIX_PAYLOAD)
            .replace("{{WHATSAPP_TEXTO}}", texto)
            .replace("{{WHATSAPP_LABEL}}", WHATSAPP_SUPORTE_LABEL)
            .replace("{{WHATSAPP}}", WHATSAPP_SUPORTE))
    return HTMLResponse(html)


@router.get("/status")
async def status_assinatura(request: Request):
    """Consumido pelo banner do portal."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse({"acesso": False, "status": "expirada"}, status_code=401)
    u = await user_service.get_por_id(user_id)
    est = assinatura_service.estado(u)
    return JSONResponse({
        "status":   est["status"],
        "acesso":   est["acesso"],
        "em_trial": est["em_trial"],
        "dias":     est["dias"],
        "pago_ate": est["pago_ate"].strftime("%d/%m/%Y") if est.get("pago_ate") else None,
    })
