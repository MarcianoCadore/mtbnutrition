import secrets
import hmac
import hashlib
import logging
import re
import time

from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from contextlib import asynccontextmanager

from app.tasks.scheduler import start_scheduler, stop_scheduler
from app.routes import workout, nutrition, whatsapp, portal
from app.services import user_service
from app.services.whatsapp_service import send_message
from app.services.mongo_service import get_db
from config.settings import settings

logger = logging.getLogger(__name__)

# ─── Segredo de assinatura ────────────────────────────────────────────────────
# Prioridade: SECRET_KEY → PORTAL_PASSWORD → "dev-secret-mtb"
_SEGREDO: str = settings.SECRET_KEY or settings.PORTAL_PASSWORD or "dev-secret-mtb"


# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Garante índices únicos em db.users ao iniciar
    try:
        await user_service.garantir_indices()
        logger.info("Índices de usuários verificados/criados com sucesso.")
    except Exception as exc:
        logger.error("Falha ao garantir índices de usuários: %s", exc)
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="MTB Nutrition Bot",
    description="Plano alimentar inteligente para ciclistas MTB com notificações WhatsApp",
    version="1.0.0",
    lifespan=lifespan,
)


# ─── Configuração do cookie e caminhos públicos ───────────────────────────────

_COOKIE = "mtb_auth"

# Paths liberados sem login: health check, tela de login/cadastro e webhook Twilio.
# O callback do Strava (/workout/strava/callback) é público porque o Strava redireciona
# sem cookie de sessão; a identificação do usuário ocorre via parâmetro state=user_id.
_PUBLIC_PATHS = {
    "/health",
    "/login",
    "/logout",
    "/signup",
    "/verificar",
    "/reenviar-codigo",
    "/whatsapp/webhook",
    "/workout/strava/callback",
}


# ─── Token com identidade de usuário ─────────────────────────────────────────

def _assinar(user_id: str, ts: int) -> str:
    """Assinatura HMAC-SHA256 de (user_id + timestamp)."""
    return hmac.new(
        _SEGREDO.encode(),
        f"{user_id}:{ts}".encode(),
        hashlib.sha256,
    ).hexdigest()


def _gerar_token(user_id: str) -> str:
    """Gera um token de sessão no formato `{user_id}.{ts}.{sig}`."""
    ts = int(time.time())
    sig = _assinar(user_id, ts)
    return f"{user_id}.{ts}.{sig}"


def _token_valido(token: str) -> str | None:
    """Valida assinatura E idade do token.

    Retorna o `user_id` se o token for válido; caso contrário, retorna None.
    """
    try:
        partes = token.split(".", 2)
        if len(partes) != 3:
            return None
        user_id, ts_str, sig = partes
        ts = int(ts_str)
    except (ValueError, AttributeError):
        return None

    if not hmac.compare_digest(sig, _assinar(user_id, ts)):
        return None

    idade = int(time.time()) - ts
    if not (0 <= idade <= settings.PORTAL_SESSAO_MIN * 60):
        return None

    return user_id


def _set_auth_cookie(resp, token: str) -> None:
    """Grava o cookie de autenticação como cookie de SESSÃO (sem max_age/expires)."""
    resp.set_cookie(_COOKIE, token, httponly=True, samesite="lax")


# ─── Middleware de autenticação ───────────────────────────────────────────────

@app.middleware("http")
async def auth(request: Request, call_next):
    """Protege todo o portal por cookie de sessão baseado em user_id."""
    if request.url.path in _PUBLIC_PATHS:
        return await call_next(request)

    token = request.cookies.get(_COOKIE, "")
    user_id = _token_valido(token) if token else None

    if user_id:
        request.state.user_id = user_id
        response = await call_next(request)
        # renova a janela de inatividade a cada requisição autenticada
        _set_auth_cookie(response, _gerar_token(user_id))
        return response

    # Não autenticado (ou sessão expirada) → redireciona para login
    return RedirectResponse(url="/login", status_code=303)


# ─── Routers ─────────────────────────────────────────────────────────────────

app.include_router(portal.router,    prefix="/portal",    tags=["Portal"])
app.include_router(workout.router,   prefix="/workout",   tags=["Treinos"])
app.include_router(nutrition.router, prefix="/nutrition", tags=["Nutrição"])
app.include_router(whatsapp.router,  prefix="/whatsapp",  tags=["WhatsApp"])


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}


# ─── HTML helpers ─────────────────────────────────────────────────────────────

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
    .login-link { text-align:center; margin-top:16px; font-size:.88rem; color:var(--muted); }
    .login-link a { color:var(--green); text-decoration:none; font-weight:600; }
    .login-link a:hover { text-decoration:underline; }
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
      <div class="login-link"><a href="/signup">Criar conta</a></div>
    </div>
  </form>
</body>
</html>"""

SIGNUP_HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>MTB Nutrition — Criar Conta</title>
  <style>
    :root { --green:#128c7e; --bg:#f0f2f5; --card:#fff; --text:#1a1a2e; --muted:#888; --border:#e0e0e0; }
    * { box-sizing:border-box; margin:0; padding:0; }
    body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; background:var(--bg); color:var(--text); min-height:100vh; display:flex; align-items:center; justify-content:center; padding:20px; }
    .card { background:var(--card); border-radius:16px; box-shadow:0 6px 30px rgba(0,0,0,.12); width:100%; max-width:480px; overflow:hidden; }
    .card-head { background:var(--green); color:#fff; padding:24px; text-align:center; }
    .card-head .logo { font-size:1.3rem; font-weight:700; }
    .card-head .sub { font-size:.82rem; opacity:.85; margin-top:4px; }
    .card-body { padding:24px; }
    fieldset { border:1.5px solid var(--border); border-radius:10px; padding:14px 16px; margin-bottom:18px; }
    legend { font-size:.75rem; font-weight:700; text-transform:uppercase; letter-spacing:.5px; color:var(--muted); padding:0 6px; }
    label { display:block; font-size:.72rem; font-weight:700; text-transform:uppercase; letter-spacing:.5px; color:var(--muted); margin:10px 0 4px; }
    label:first-of-type { margin-top:0; }
    input[type=text],input[type=password],input[type=number],input[type=tel],select {
      width:100%; border:1.5px solid var(--border); border-radius:8px; padding:10px 12px; font-size:.95rem; font-family:inherit; outline:none; transition:border-color .2s;
    }
    input:focus,select:focus { border-color:var(--green); }
    .dias { display:flex; flex-wrap:wrap; gap:8px; margin-top:4px; }
    .dias label { font-size:.8rem; font-weight:600; text-transform:none; letter-spacing:0; color:var(--text); display:flex; align-items:center; gap:4px; margin:0; }
    .check-row { display:flex; align-items:center; gap:8px; margin-top:6px; }
    .check-row label { margin:0; text-transform:none; letter-spacing:0; font-size:.9rem; color:var(--text); }
    .btn { width:100%; background:var(--green); color:#fff; border:none; border-radius:10px; padding:14px; font-size:1rem; font-weight:700; cursor:pointer; transition:background .2s; margin-top:4px; }
    .btn:hover { background:#0e7166; }
    .err { background:#fdecea; color:#c62828; border-radius:9px; padding:10px 12px; font-size:.85rem; font-weight:600; margin-bottom:14px; text-align:center; }
    .login-link { text-align:center; margin-top:14px; font-size:.88rem; color:var(--muted); }
    .login-link a { color:var(--green); text-decoration:none; font-weight:600; }
  </style>
</head>
<body>
<form class="card" method="post" action="/signup">
  <div class="card-head">
    <div class="logo">🚵 MTB Nutrition</div>
    <div class="sub">Criar nova conta</div>
  </div>
  <div class="card-body">
    {{ERRO}}
    <fieldset>
      <legend>Acesso</legend>
      <label for="login">Login (usuário)</label>
      <input id="login" name="login" type="text" autocomplete="username" required>
      <label for="senha">Senha</label>
      <input id="senha" name="senha" type="password" autocomplete="new-password" required>
      <label for="nome">Nome completo</label>
      <input id="nome" name="nome" type="text" required>
      <label for="telefone">Telefone WhatsApp</label>
      <input id="telefone" name="telefone" type="tel" placeholder="+5551999999999" required>
    </fieldset>

    <fieldset>
      <legend>Perfil físico</legend>
      <label for="idade">Idade (anos)</label>
      <input id="idade" name="idade" type="number" min="10" max="100">
      <label for="sexo">Sexo</label>
      <select id="sexo" name="sexo">
        <option value="M">Masculino</option>
        <option value="F">Feminino</option>
      </select>
      <label for="peso_kg">Peso (kg)</label>
      <input id="peso_kg" name="peso_kg" type="number" step="0.1" min="30" max="200">
      <label for="altura_cm">Altura (cm)</label>
      <input id="altura_cm" name="altura_cm" type="number" min="100" max="250">
      <label for="fc_max">FC máxima (bpm)</label>
      <input id="fc_max" name="fc_max" type="number" min="100" max="230">
      <small style="color:#888;">Frequência Cardíaca Máxima — maior número de batimentos por minuto que seu coração pode atingir. Se não souber, deixe em branco (estimaremos pelo cálculo 220 − sua idade).</small>
    </fieldset>

    <fieldset>
      <legend>Preferências de treino</legend>
      <label for="objetivo">Objetivo</label>
      <select id="objetivo" name="objetivo">
        <option value="performance">Performance</option>
        <option value="emagrecimento">Emagrecimento</option>
        <option value="base">Base aeróbica</option>
        <option value="prova">Preparação para prova</option>
      </select>
      <label>Dias de treino</label>
      <div class="dias">
        <label><input type="checkbox" name="dias_treino" value="0"> Seg</label>
        <label><input type="checkbox" name="dias_treino" value="1"> Ter</label>
        <label><input type="checkbox" name="dias_treino" value="2"> Qua</label>
        <label><input type="checkbox" name="dias_treino" value="3"> Qui</label>
        <label><input type="checkbox" name="dias_treino" value="4"> Sex</label>
        <label><input type="checkbox" name="dias_treino" value="5"> Sáb</label>
        <label><input type="checkbox" name="dias_treino" value="6"> Dom</label>
      </div>
      <div class="check-row" style="margin-top:12px;">
        <input type="checkbox" id="perder_peso" name="perder_peso" value="1">
        <label for="perder_peso">Quero perder peso</label>
      </div>
    </fieldset>

    <fieldset>
      <legend>Integração</legend>
      <label for="integracao_tipo">Plataforma de treinos</label>
      <select id="integracao_tipo" name="integracao_tipo">
        <option value="none">Nenhuma</option>
        <option value="garmin">Garmin Connect</option>
        <option value="strava">Strava</option>
      </select>
    </fieldset>

    <button class="btn" type="submit">Criar conta</button>
    <div class="login-link"><a href="/login">Já tenho conta — Entrar</a></div>
  </div>
</form>
</body>
</html>"""

VERIFICAR_HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>MTB Nutrition — Verificar Telefone</title>
  <style>
    :root { --green:#128c7e; --bg:#f0f2f5; --card:#fff; --text:#1a1a2e; --muted:#888; --border:#e0e0e0; }
    * { box-sizing:border-box; margin:0; padding:0; }
    body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; background:var(--bg); color:var(--text); min-height:100vh; display:flex; align-items:center; justify-content:center; padding:20px; }
    .card { background:var(--card); border-radius:16px; box-shadow:0 6px 30px rgba(0,0,0,.12); width:100%; max-width:360px; overflow:hidden; }
    .card-head { background:var(--green); color:#fff; padding:24px; text-align:center; }
    .card-head .logo { font-size:1.3rem; font-weight:700; }
    .card-head .sub { font-size:.82rem; opacity:.85; margin-top:4px; }
    .card-body { padding:24px; }
    .info { font-size:.9rem; color:var(--muted); margin-bottom:16px; text-align:center; }
    label { display:block; font-size:.72rem; font-weight:700; text-transform:uppercase; letter-spacing:.5px; color:var(--muted); margin-bottom:6px; }
    input[type=text] { width:100%; border:1.5px solid var(--border); border-radius:8px; padding:12px 14px; font-size:1.4rem; letter-spacing:6px; text-align:center; font-family:monospace; outline:none; transition:border-color .2s; margin-bottom:16px; }
    input:focus { border-color:var(--green); }
    .btn { width:100%; background:var(--green); color:#fff; border:none; border-radius:10px; padding:14px; font-size:1rem; font-weight:700; cursor:pointer; transition:background .2s; }
    .btn:hover { background:#0e7166; }
    .err { background:#fdecea; color:#c62828; border-radius:9px; padding:10px 12px; font-size:.85rem; font-weight:600; margin-bottom:14px; text-align:center; }
    .reenviar { margin-top:14px; text-align:center; font-size:.85rem; color:var(--muted); }
    .reenviar form { display:inline; }
    .reenviar button { background:none; border:none; color:var(--green); font-weight:600; cursor:pointer; font-size:.85rem; text-decoration:underline; }
  </style>
</head>
<body>
<div class="card">
  <div class="card-head">
    <div class="logo">✅ Cadastro Realizado</div>
    <div class="sub">Aguardando liberação</div>
  </div>
  <div class="card-body">
    <p class="info" style="text-align:center; font-size:1rem; color:#333; line-height:1.6;">
      Cadastro realizado com sucesso!
    </p>
    <p class="info" style="text-align:center; font-size:.95rem; color:#555; line-height:1.6;">
      Favor entrar em contato com o administrador da plataforma informando que já realizou o cadastro para que seu acesso seja liberado.
    </p>
  </div>
</div>
</body>
</html>"""


def _render_verificar(tel: str, erro: str = "") -> str:
    erro_html = f"<div class='err'>{erro}</div>" if erro else ""
    return (VERIFICAR_HTML
            .replace("{{TEL}}", tel)
            .replace("{{TELEFONE_DISPLAY}}", tel)
            .replace("{{ERRO}}", erro_html))


# ─── Normalização de telefone ─────────────────────────────────────────────────

def _normalizar_telefone(tel: str) -> str:
    """Normaliza para E.164: '+' seguido apenas de dígitos.

    Exemplos de entrada aceitos:
        +55 51 99999-9999  →  +5551999999999
        5551999999999      →  +5551999999999
        (51) 99999-9999    →  +5199999999999  (sem DDI — não adiciona 55)
    """
    digitos = re.sub(r"\D", "", tel)
    if tel.strip().startswith("+"):
        return "+" + digitos
    # Se não veio com '+', presume que já inclui o DDI
    return "+" + digitos


# ─── OTP ─────────────────────────────────────────────────────────────────────

def _gerar_otp() -> str:
    """Gera um código OTP de 6 dígitos usando secrets.randbelow."""
    return "".join(str(secrets.randbelow(10)) for _ in range(6))


async def _enviar_otp(telefone: str) -> str:
    """Gera, persiste e envia (via WhatsApp) um OTP para o telefone informado.

    Retorna o código gerado (útil apenas para testes/log).
    """
    db = get_db()
    codigo = _gerar_otp()
    expira_em = datetime.now(timezone.utc) + timedelta(minutes=settings.OTP_EXPIRA_MIN)

    # Upsert: _id = telefone para garantir unicidade e sobrescrever OTPs antigos
    await db.verificacoes.update_one(
        {"_id": telefone},
        {"$set": {
            "codigo_hash": user_service.hash_senha(codigo),
            "expira_em": expira_em,
            "tentativas": 0,
        }},
        upsert=True,
    )

    mensagem = f"Seu código de verificação MTB Nutrition é: {codigo}"
    try:
        await send_message(telefone, mensagem)
    except Exception as exc:
        # Twilio não configurado ou indisponível — loga o código para testes locais
        logger.warning("OTP de %s: %s (falha ao enviar via WhatsApp: %s)", telefone, codigo, exc)

    return codigo


# ─── Rotas de autenticação ────────────────────────────────────────────────────

@app.get("/login", include_in_schema=False)
async def login_form(erro: int = 0):
    erro_html = "<div class='login-err'>Usuário ou senha incorretos</div>" if erro else ""
    return HTMLResponse(LOGIN_HTML.replace("{{ERRO}}", erro_html))


@app.post("/login", include_in_schema=False)
async def login_submit(request: Request):
    form = await request.form()
    usuario = str(form.get("usuario", "")).strip().lower()
    senha = str(form.get("senha", ""))

    u = await user_service.get_por_login(usuario)
    if not u or not user_service.verificar_senha(senha, u.get("senha_hash", "")):
        return RedirectResponse(url="/login?erro=1", status_code=303)

    # Conta ainda não verificou o telefone
    if not u.get("telefone_verificado"):
        tel = u.get("telefone", "")
        return RedirectResponse(url=f"/verificar?tel={tel}", status_code=303)

    token = _gerar_token(str(u["_id"]))
    resp = RedirectResponse(url="/", status_code=303)
    _set_auth_cookie(resp, token)
    return resp


@app.get("/logout", include_in_schema=False)
async def logout():
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie(_COOKIE)
    return resp


# ─── Cadastro ─────────────────────────────────────────────────────────────────

@app.get("/signup", include_in_schema=False)
async def signup_form():
    return HTMLResponse(SIGNUP_HTML.replace("{{ERRO}}", ""))


@app.post("/signup", include_in_schema=False)
async def signup_submit(request: Request):
    form = await request.form()

    # Coleta e normaliza campos
    login = str(form.get("login", "")).strip().lower()
    senha = str(form.get("senha", "")).strip()
    nome = str(form.get("nome", "")).strip()
    telefone_raw = str(form.get("telefone", "")).strip()
    telefone = _normalizar_telefone(telefone_raw) if telefone_raw else ""

    perfil = {
        "idade": form.get("idade") or None,
        "peso_kg": form.get("peso_kg") or None,
        "altura_cm": form.get("altura_cm") or None,
        "sexo": form.get("sexo") or "M",
        "fc_max": form.get("fc_max") or None,
        "limiar_bpm": None,
    }

    objetivo = str(form.get("objetivo", "performance"))
    dias_treino_raw = form.getlist("dias_treino")
    dias_treino = [int(d) for d in dias_treino_raw if d.isdigit()]
    perder_peso = bool(form.get("perder_peso"))
    integracao_tipo = str(form.get("integracao_tipo", "none"))

    dados = {
        "login": login,
        "senha": senha,
        "nome": nome,
        "telefone": telefone,
        "telefone_verificado": False,
        "perfil": perfil,
        "preferencias": {
            "objetivo": objetivo,
            "dias_treino": dias_treino,
            "perder_peso": perder_peso,
        },
        "nutricao": {
            "meta_peso_kg": None,
            "meta_proteina_g": None,
        },
        "integracao": {
            "tipo": integracao_tipo,
        },
        "whatsapp": {"ativo": False},
    }

    def _erro_signup(msg: str):
        erro_html = f"<div class='err'>{msg}</div>"
        return HTMLResponse(SIGNUP_HTML.replace("{{ERRO}}", erro_html))

    try:
        await user_service.criar_usuario(dados)
    except ValueError as exc:
        return _erro_signup(str(exc))
    except Exception as exc:
        err_str = str(exc)
        if "11000" in err_str or "duplicate key" in err_str:
            if "telefone" in err_str:
                return _erro_signup("Este número de WhatsApp já está cadastrado. Use outro número ou faça login.")
            if "login" in err_str:
                return _erro_signup("Este usuário já está cadastrado. Escolha outro nome de usuário ou faça login.")
            return _erro_signup("Já existe uma conta com esses dados. Verifique e tente novamente.")
        logger.error("Erro ao criar usuário: %s", exc)
        return _erro_signup("Erro interno ao criar conta. Tente novamente.")

    # Gera e envia OTP
    await _enviar_otp(telefone)

    return RedirectResponse(url=f"/verificar?tel={telefone}", status_code=303)


# ─── Verificação OTP ──────────────────────────────────────────────────────────

@app.get("/verificar", include_in_schema=False)
async def verificar_form(tel: str = "", erro: int = 0):
    msg = ""
    if erro == 1:
        msg = "Código incorreto. Tente novamente."
    elif erro == 2:
        msg = "Código expirado. Solicite um novo código."
    elif erro == 3:
        msg = "Muitas tentativas incorretas. Solicite um novo código."
    return HTMLResponse(_render_verificar(tel, msg))


@app.post("/verificar", include_in_schema=False)
async def verificar_submit(request: Request):
    form = await request.form()
    tel = str(form.get("tel", "")).strip()
    codigo = str(form.get("codigo", "")).strip()

    db = get_db()
    doc = await db.verificacoes.find_one({"_id": tel})

    if not doc:
        return RedirectResponse(url=f"/verificar?tel={tel}&erro=2", status_code=303)

    # Verifica expiração
    expira_em = doc.get("expira_em")
    if expira_em:
        # expira_em pode ser offset-naive (sem tz) vindo do MongoDB
        if expira_em.tzinfo is None:
            expira_em = expira_em.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expira_em:
            await db.verificacoes.delete_one({"_id": tel})
            return RedirectResponse(url=f"/verificar?tel={tel}&erro=2", status_code=303)

    # Verifica limite de tentativas
    tentativas = doc.get("tentativas", 0)
    if tentativas >= settings.OTP_MAX_TENTATIVAS:
        return RedirectResponse(url=f"/verificar?tel={tel}&erro=3", status_code=303)

    # Verifica código
    if user_service.verificar_senha(codigo, doc.get("codigo_hash", "")):
        # Código correto: atualiza usuário e faz auto-login
        u = await user_service.get_por_telefone(tel)
        if u:
            await user_service.atualizar_usuario(
                u["_id"],
                {"telefone_verificado": True, "whatsapp.ativo": True},
            )
        await db.verificacoes.delete_one({"_id": tel})

        user_id = str(u["_id"]) if u else ""
        token = _gerar_token(user_id)
        # Após confirmar o cadastro, leva direto à tela de conectar a conta.
        resp = RedirectResponse(url="/workout/integracao", status_code=303)
        _set_auth_cookie(resp, token)
        return resp

    # Código incorreto: incrementa tentativas
    await db.verificacoes.update_one({"_id": tel}, {"$inc": {"tentativas": 1}})
    return RedirectResponse(url=f"/verificar?tel={tel}&erro=1", status_code=303)


@app.post("/reenviar-codigo", include_in_schema=False)
async def reenviar_codigo(request: Request):
    form = await request.form()
    tel = str(form.get("tel", "")).strip()
    await _enviar_otp(tel)
    return RedirectResponse(url=f"/verificar?tel={tel}", status_code=303)


# ─── Root ─────────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/portal/")
