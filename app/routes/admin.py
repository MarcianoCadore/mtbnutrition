from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from bson import ObjectId

from app.services.mongo_service import get_db

router = APIRouter()

_ADMIN_LOGIN = "marciano"

_HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Admin — MTB Nutrition</title>
  <style>
    :root { --green:#128c7e; --green2:#25d366; --bg:#f0f2f5; --card:#fff; --text:#1a1a2e; --muted:#888; --border:#e0e0e0; }
    * { box-sizing:border-box; margin:0; padding:0; }
    body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; background:var(--bg); color:var(--text); min-height:100vh; }

    nav { background:var(--green); color:#fff; padding:14px 20px; display:flex; align-items:center; gap:12px; box-shadow:0 2px 8px rgba(0,0,0,.2); }
    nav .logo { font-size:1.15rem; font-weight:700; }
    nav .badge-admin { background:rgba(255,255,255,.22); color:#fff; font-size:.7rem; font-weight:800; text-transform:uppercase; letter-spacing:.8px; padding:3px 9px; border-radius:20px; }
    nav .nav-links { margin-left:auto; display:flex; gap:16px; align-items:center; }
    nav .nav-links a { color:#fff; text-decoration:none; font-size:.88rem; opacity:.85; }
    nav .nav-links a:hover { opacity:1; text-decoration:underline; }

    main { max-width:700px; margin:0 auto; padding:24px 16px 80px; }
    h1 { font-size:1.25rem; font-weight:800; margin-bottom:4px; }
    .sub-title { color:var(--muted); font-size:.85rem; margin-bottom:20px; }

    /* Stats */
    .stats { display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin-bottom:20px; }
    .stat { background:var(--card); border-radius:10px; padding:12px 14px; box-shadow:0 1px 4px rgba(0,0,0,.08); }
    .stat .val { font-size:1.6rem; font-weight:800; color:var(--green); }
    .stat .lbl { font-size:.7rem; color:var(--muted); margin-top:1px; }

    /* Cards de usuário */
    .user-list { display:flex; flex-direction:column; gap:12px; }
    .user-card { background:var(--card); border-radius:12px; padding:16px; box-shadow:0 1px 4px rgba(0,0,0,.08); }
    .user-head { display:flex; align-items:center; gap:10px; margin-bottom:12px; }
    .user-avatar { width:40px; height:40px; border-radius:50%; background:var(--green); color:#fff; display:flex; align-items:center; justify-content:center; font-weight:800; font-size:1rem; flex-shrink:0; }
    .user-info { flex:1; min-width:0; }
    .user-login { font-family:monospace; font-weight:700; font-size:.9rem; }
    .user-nome { font-size:.82rem; color:var(--muted); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .user-tel { font-size:.78rem; color:var(--muted); margin-top:1px; }
    .user-cadastro { font-size:.72rem; color:var(--muted); margin-top:2px; }
    .pending-banner { background:#fff8e1; border:1.5px solid #f59e0b; border-radius:10px; padding:12px 16px; margin-bottom:18px; font-size:.88rem; color:#92400e; display:none; }
    .pending-banner b { font-size:1rem; }

    .user-rows { display:flex; flex-direction:column; gap:8px; }
    .user-row { display:flex; align-items:center; justify-content:space-between; gap:8px; }
    .user-row-label { font-size:.75rem; color:var(--muted); font-weight:600; text-transform:uppercase; letter-spacing:.4px; flex-shrink:0; }

    .badge { display:inline-flex; align-items:center; gap:4px; padding:3px 9px; border-radius:20px; font-size:.72rem; font-weight:700; white-space:nowrap; }
    .badge.on   { background:#e6f9f0; color:#128c7e; }
    .badge.off  { background:#fef2f2; color:#c0392b; }
    .badge.pend { background:#fff8e1; color:#e67e22; }

    .btn-sm { border:none; border-radius:20px; padding:5px 14px; font-size:.78rem; font-weight:700; cursor:pointer; transition:all .15s; white-space:nowrap; flex-shrink:0; }
    .btn-habilitar { background:#27ae60; color:#fff; }
    .btn-habilitar:hover { background:#219a52; }
    .btn-bloquear  { background:#e74c3c; color:#fff; }
    .btn-bloquear:hover  { background:#c0392b; }
    .btn-chat-on   { background:var(--green2); color:#fff; }
    .btn-chat-on:hover   { background:#1db954; }
    .btn-chat-off  { background:#95a5a6; color:#fff; }
    .btn-chat-off:hover  { background:#7f8c8d; }
    .btn-sm:disabled { opacity:.45; cursor:not-allowed; }

    .toast { position:fixed; bottom:24px; left:50%; transform:translateX(-50%); background:#1a1a2e; color:#fff; padding:10px 22px; border-radius:10px; font-size:.88rem; opacity:0; pointer-events:none; transition:opacity .3s; z-index:9999; white-space:nowrap; }
    .toast.show { opacity:1; }

    @media(max-width:480px) {
      .stats { grid-template-columns:repeat(2,1fr); }
    }
  </style>
</head>
<body>
<nav>
  <span class="logo">MTB Nutrition</span>
  <span class="badge-admin">Admin</span>
  <div class="nav-links">
    <a href="/">Portal</a>
    <a href="/logout">Sair</a>
  </div>
</nav>
<main>
  <h1>Administração</h1>
  <p class="sub-title">Gerencie acesso e chat por usuário.</p>

  <div id="pending-banner" class="pending-banner"></div>
  <div class="stats" id="stats"></div>
  <div class="user-list" id="user-list"></div>
</main>
<div class="toast" id="toast"></div>

<script>
const USERS = __USERS_JSON__;

function acessoAtivo(u) { return u.telefone_verificado === true; }
function chatAtivo(u)   { return (u.features || {}).chat !== false; }

function iniciais(u) {
  const n = (u.nome || u.login || '?');
  return n.split(' ').map(p => p[0]).slice(0,2).join('').toUpperCase();
}

function renderStats() {
  const total   = USERS.length;
  const ativos  = USERS.filter(acessoAtivo).length;
  const pend    = total - ativos;
  const comChat = USERS.filter(chatAtivo).length;
  document.getElementById('stats').innerHTML = `
    <div class="stat"><div class="val">${total}</div><div class="lbl">Usuários</div></div>
    <div class="stat"><div class="val">${ativos}</div><div class="lbl">Com acesso</div></div>
    <div class="stat"><div class="val">${pend}</div><div class="lbl">Aguardando</div></div>
    <div class="stat"><div class="val">${comChat}</div><div class="lbl">Chat ativo</div></div>`;
}

function renderCard(u) {
  const acesso = acessoAtivo(u);
  const chat   = chatAtivo(u);
  const badgeAcesso = acesso
    ? '<span class="badge on">✓ Habilitado</span>'
    : '<span class="badge pend">⏳ Aguardando</span>';
  const badgeChat = chat
    ? '<span class="badge on">✓ Ativo</span>'
    : '<span class="badge off">✗ Inativo</span>';
  const btnAcesso = acesso
    ? `<button class="btn-sm btn-bloquear"  id="ba-${u.id}" onclick="toggleAcesso('${u.id}',true)">Bloquear</button>`
    : `<button class="btn-sm btn-habilitar" id="ba-${u.id}" onclick="toggleAcesso('${u.id}',false)">Habilitar</button>`;
  const btnChat = chat
    ? `<button class="btn-sm btn-chat-off" id="bc-${u.id}" onclick="toggleChat('${u.id}',true)">Desativar</button>`
    : `<button class="btn-sm btn-chat-on"  id="bc-${u.id}" onclick="toggleChat('${u.id}',false)">Ativar</button>`;
  return `<div class="user-card" id="row-${u.id}">
    <div class="user-head">
      <div class="user-avatar">${iniciais(u)}</div>
      <div class="user-info">
        <div class="user-login">${u.login}</div>
        <div class="user-nome">${u.nome || '—'}</div>
        <div class="user-tel">${u.tel || '—'}</div>
        ${u.criado_em ? `<div class="user-cadastro">📅 Cadastro: ${u.criado_em}</div>` : ''}
      </div>
    </div>
    <div class="user-rows">
      <div class="user-row">
        <span class="user-row-label">Acesso</span>
        <div style="display:flex;align-items:center;gap:8px">${badgeAcesso}${btnAcesso}</div>
      </div>
      <div class="user-row">
        <span class="user-row-label">Chat</span>
        <div style="display:flex;align-items:center;gap:8px">${badgeChat}${btnChat}</div>
      </div>
    </div>
  </div>`;
}

function renderAll() {
  renderStats();
  document.getElementById('user-list').innerHTML = USERS.map(renderCard).join('');
  const pend = USERS.filter(u => !acessoAtivo(u));
  const banner = document.getElementById('pending-banner');
  if (pend.length > 0) {
    banner.style.display = 'block';
    const nomes = pend.map(u => u.nome || u.login).join(', ');
    banner.innerHTML = `<b>⏳ ${pend.length} usuário${pend.length > 1 ? 's' : ''} aguardando acesso:</b> ${nomes}<br><span style="font-size:.8rem">Clique em <b>Habilitar</b> no cartão do usuário para liberar o acesso.</span>`;
  } else {
    banner.style.display = 'none';
  }
}

async function toggleAcesso(id, currentAtivo) {
  const btn = document.getElementById('ba-' + id);
  btn.disabled = true;
  const novoAtivo = !currentAtivo;
  const res = await fetch('/admin/toggle-acesso', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({user_id: id, ativo: novoAtivo})
  });
  if (res.ok) {
    const u = USERS.find(x => x.id === id);
    u.telefone_verificado = novoAtivo;
    document.getElementById('row-' + id).outerHTML = renderCard(u);
    renderStats();
    showToast(novoAtivo ? 'Usuário habilitado.' : 'Usuário bloqueado.');
  } else { btn.disabled = false; showToast('Erro ao atualizar acesso.'); }
}

async function toggleChat(id, currentAtivo) {
  const btn = document.getElementById('bc-' + id);
  btn.disabled = true;
  const novoAtivo = !currentAtivo;
  const res = await fetch('/admin/toggle-chat', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({user_id: id, ativo: novoAtivo})
  });
  if (res.ok) {
    const u = USERS.find(x => x.id === id);
    u.features = u.features || {};
    u.features.chat = novoAtivo;
    document.getElementById('row-' + id).outerHTML = renderCard(u);
    renderStats();
    showToast(novoAtivo ? 'Chat ativado.' : 'Chat desativado.');
  } else { btn.disabled = false; showToast('Erro ao atualizar chat.'); }
}

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2500);
}

renderAll();
</script>
</body>
</html>"""


async def _require_admin(request: Request):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return None
    db = get_db()
    u = await db.users.find_one({"_id": ObjectId(user_id)}, {"login": 1})
    if not u or u.get("login") != _ADMIN_LOGIN:
        return None
    return u


@router.get("", response_class=HTMLResponse)
async def admin_page(request: Request):
    admin = await _require_admin(request)
    if not admin:
        return HTMLResponse("<h3>Acesso negado.</h3>", status_code=403)

    db = get_db()
    cursor = db.users.find(
        {}, {"login": 1, "nome": 1, "telefone": 1, "telefone_verificado": 1, "features": 1, "criado_em": 1}
    )
    usuarios = await cursor.to_list(length=None)

    import json
    dados = [
        {
            "id": str(u["_id"]),
            "login": u.get("login", ""),
            "nome": u.get("nome", ""),
            "tel": u.get("telefone", ""),
            "telefone_verificado": bool(u.get("telefone_verificado", False)),
            "features": u.get("features", {}),
            "criado_em": u["criado_em"].strftime("%d/%m/%Y %H:%M") if u.get("criado_em") else "",
        }
        for u in usuarios
    ]
    # Pendentes primeiro, depois por data de cadastro (mais recentes primeiro)
    dados.sort(key=lambda x: (x["telefone_verificado"], x["criado_em"]))
    users_json = json.dumps(dados, ensure_ascii=False)
    html = _HTML.replace("__USERS_JSON__", users_json)
    return HTMLResponse(html)


@router.post("/toggle-acesso")
async def toggle_acesso(request: Request):
    admin = await _require_admin(request)
    if not admin:
        return JSONResponse({"erro": "Acesso negado."}, status_code=403)

    body = await request.json()
    user_id = body.get("user_id")
    ativo = body.get("ativo")

    if not user_id or not isinstance(ativo, bool):
        return JSONResponse({"erro": "Parâmetros inválidos."}, status_code=400)

    try:
        oid = ObjectId(user_id)
    except Exception:
        return JSONResponse({"erro": "user_id inválido."}, status_code=400)

    db = get_db()
    await db.users.update_one({"_id": oid}, {"$set": {"telefone_verificado": ativo}})
    return JSONResponse({"ok": True, "ativo": ativo})


@router.post("/toggle-chat")
async def toggle_chat(request: Request):
    admin = await _require_admin(request)
    if not admin:
        return JSONResponse({"erro": "Acesso negado."}, status_code=403)

    body = await request.json()
    user_id = body.get("user_id")
    ativo = body.get("ativo")

    if not user_id or not isinstance(ativo, bool):
        return JSONResponse({"erro": "Parâmetros inválidos."}, status_code=400)

    try:
        oid = ObjectId(user_id)
    except Exception:
        return JSONResponse({"erro": "user_id inválido."}, status_code=400)

    db = get_db()
    await db.users.update_one({"_id": oid}, {"$set": {"features.chat": ativo}})
    return JSONResponse({"ok": True, "ativo": ativo})
