import secrets
import hmac
import hashlib

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, Response, HTMLResponse
from contextlib import asynccontextmanager
from app.tasks.scheduler import start_scheduler, stop_scheduler
from app.routes import workout, nutrition, whatsapp, portal
from config.settings import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()

app = FastAPI(
    title="MTB Nutrition Bot",
    description="Plano alimentar inteligente para ciclistas MTB com notificações WhatsApp",
    version="1.0.0",
    lifespan=lifespan
)


# Paths liberados sem login (health check, tela de login e webhook da Twilio).
_PUBLIC_PATHS = {"/health", "/login", "/logout", "/whatsapp/webhook"}
_COOKIE = "mtb_auth"


def _expected_token() -> str:
    """Token de sessão derivado do usuário+senha. Muda sozinho se a senha mudar
    (invalidando cookies antigos). Não revela a senha."""
    return hmac.new(
        settings.PORTAL_PASSWORD.encode(),
        settings.PORTAL_USER.encode(),
        hashlib.sha256,
    ).hexdigest()


LOGIN_HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>MTB Nutrition — Entrar</title>
  <style>
    :root { --green:#128c7e; --green2:#25d366; --bg:#f0f2f5; --card:#fff; --text:#1a1a2e; --muted:#888; --border:#e0e0e0; }
    * { box-sizing:border-box; margin:0; padding:0; }
    body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; background:var(--bg); color:var(--text); min-height:100vh; display:flex; align-items:center; justify-content:center; padding:20px; }
    .login-card { background:var(--card); border-radius:16px; box-shadow:0 6px 30px rgba(0,0,0,.12); width:100%; max-width:380px; overflow:hidden; }
    .login-head { background:var(--green); color:#fff; padding:28px 24px; text-align:center; }
    .login-head .emoji { font-size:2.4rem; }
    .login-head .logo { font-size:1.4rem; font-weight:700; margin-top:6px; }
    .login-head .sub { font-size:.82rem; opacity:.85; margin-top:2px; }
    .login-body { padding:26px 24px 28px; }
    .login-body label { display:block; font-size:.72rem; font-weight:700; text-transform:uppercase; letter-spacing:.6px; color:var(--muted); margin-bottom:6px; }
    .login-body input { width:100%; border:1.5px solid var(--border); border-radius:9px; padding:12px 14px; font-size:1rem; font-family:inherit; outline:none; transition:border-color .2s; margin-bottom:16px; }
    .login-body input:focus { border-color:var(--green); }
    .login-btn { width:100%; background:var(--green); color:#fff; border:none; border-radius:10px; padding:14px; font-size:1rem; font-weight:700; cursor:pointer; transition:background .2s; }
    .login-btn:hover { background:#0e7166; }
    .login-err { background:#fdecea; color:#c62828; border-radius:9px; padding:10px 12px; font-size:.85rem; font-weight:600; margin-bottom:16px; text-align:center; }
  </style>
</head>
<body>
  <form class="login-card" method="post" action="/login">
    <div class="login-head">
      <div class="emoji">🚵</div>
      <div class="logo">MTB Nutrition</div>
      <div class="sub">Portal de Treinos</div>
    </div>
    <div class="login-body">
      {{ERRO}}
      <label for="usuario">Usuário</label>
      <input id="usuario" name="usuario" autocomplete="username" autofocus required>
      <label for="senha">Senha</label>
      <input id="senha" name="senha" type="password" autocomplete="current-password" required>
      <button class="login-btn" type="submit">Entrar</button>
    </div>
  </form>
</body>
</html>"""


@app.middleware("http")
async def auth(request: Request, call_next):
    """Protege todo o portal por cookie de sessão. Se PORTAL_PASSWORD não estiver
    configurado, o acesso é liberado (modo dev local)."""
    if not settings.PORTAL_PASSWORD or request.url.path in _PUBLIC_PATHS:
        return await call_next(request)

    token = request.cookies.get(_COOKIE, "")
    if token and secrets.compare_digest(token, _expected_token()):
        return await call_next(request)

    # Não autenticado → manda para a tela de login.
    return RedirectResponse(url="/login", status_code=303)


app.include_router(portal.router,   prefix="/portal",    tags=["Portal"])
app.include_router(workout.router,  prefix="/workout",   tags=["Treinos"])
app.include_router(nutrition.router,prefix="/nutrition", tags=["Nutrição"])
app.include_router(whatsapp.router, prefix="/whatsapp",  tags=["WhatsApp"])


@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}


@app.get("/login", include_in_schema=False)
async def login_form(erro: int = 0):
    erro_html = "<div class='login-err'>Usuário ou senha incorretos</div>" if erro else ""
    return HTMLResponse(LOGIN_HTML.replace("{{ERRO}}", erro_html))


@app.post("/login", include_in_schema=False)
async def login_submit(request: Request):
    form = await request.form()
    user = str(form.get("usuario", ""))
    pwd = str(form.get("senha", ""))
    ok = (secrets.compare_digest(user, settings.PORTAL_USER)
          and secrets.compare_digest(pwd, settings.PORTAL_PASSWORD))
    if not ok:
        return RedirectResponse(url="/login?erro=1", status_code=303)
    resp = RedirectResponse(url="/", status_code=303)
    # Cookie de SESSÃO (sem max_age/expires): o navegador o apaga ao fechar,
    # então fechar o navegador ou desligar o notebook desloga do portal.
    resp.set_cookie(_COOKIE, _expected_token(), httponly=True,
                    samesite="lax")
    return resp


@app.get("/logout", include_in_schema=False)
async def logout():
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie(_COOKIE)
    return resp


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/portal/")
