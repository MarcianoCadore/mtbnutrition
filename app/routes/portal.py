from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>MTB Nutrition — Portal de Treinos</title>
  <style>
    :root {
      --green: #128c7e; --green2: #25d366; --bg: #f0f2f5;
      --card: #fff; --text: #1a1a2e; --muted: #888; --border: #e0e0e0;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }

    nav { background: var(--green); color: #fff; padding: 14px 24px; display: flex; align-items: center; gap: 12px; box-shadow: 0 2px 8px rgba(0,0,0,.2); }
    nav .logo { font-size: 1.35rem; font-weight: 700; }
    nav .sub  { font-size: 0.8rem; opacity: .8; }
    nav .nav-links { margin-left: auto; display: flex; gap: 16px; }
    nav .nav-links a { color: #fff; text-decoration: none; font-size: 0.88rem; opacity: .85; white-space: nowrap; }
    nav .nav-links a:hover { opacity: 1; text-decoration: underline; }

    main { max-width: 1400px; margin: 0 auto; padding: 24px 20px 80px; }

    .week-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 24px; flex-wrap: wrap; }
    .week-bar .arrow { background: #fff; border: 1.5px solid var(--border); border-radius: 8px; width: 38px; height: 38px; cursor: pointer; font-size: 1.1rem; display: flex; align-items: center; justify-content: center; transition: all .15s; }
    .week-bar .arrow:hover { border-color: var(--green); color: var(--green); }
    .week-label { font-size: 1.05rem; font-weight: 700; flex: 1; text-align: center; }
    .today-btn { background: none; border: none; color: var(--green); font-size: 0.85rem; text-decoration: underline; cursor: pointer; }

    .card { background: #fff; border-radius: 12px; padding: 20px; margin-bottom: 20px; box-shadow: 0 1px 4px rgba(0,0,0,.08); }
    .section-label { font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: .8px; color: var(--muted); margin-bottom: 8px; }
    .card textarea { width: 100%; border: 1.5px solid var(--border); border-radius: 8px; padding: 10px 12px; font-size: .95rem; font-family: inherit; resize: vertical; min-height: 72px; outline: none; transition: border-color .2s; line-height: 1.5; }
    .card textarea:focus { border-color: var(--green); }

    .days-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 10px; margin-bottom: 24px; }
    @media(max-width:1000px){ .days-grid { grid-template-columns: repeat(4,1fr); } }
    @media(max-width:640px) { .days-grid { grid-template-columns: repeat(2,1fr); } }
    @media(max-width:360px) { .days-grid { grid-template-columns: 1fr; } }

    .day-card { background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,.08); transition: box-shadow .2s; }
    .day-card:hover { box-shadow: 0 4px 14px rgba(0,0,0,.13); }
    .day-card.today { outline: 2.5px solid var(--green); }
    .day-head { padding: 10px 12px; color: #fff; }
    .day-name { font-weight: 700; font-size: .88rem; }
    .day-date { font-size: .73rem; opacity: .85; }
    .day-body { padding: 12px; display: flex; flex-direction: column; gap: 8px; }
    .day-body label { font-size: .7rem; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: .5px; display: block; margin-bottom: 2px; }
    .day-body select, .day-body input[type=number], .day-body textarea {
      width: 100%; border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px;
      font-size: .85rem; font-family: inherit; outline: none; transition: border-color .2s; background: #fff;
    }
    .day-body select:focus, .day-body input:focus, .day-body textarea:focus { border-color: var(--green); }
    .day-body textarea { resize: vertical; min-height: 46px; font-size: .82rem; }
    .row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }

    .fit-area { border: 1.5px dashed var(--border); border-radius: 6px; padding: 8px; text-align: center; transition: border-color .2s; }
    .fit-area:hover { border-color: var(--green); }
    .fit-area input[type=file] { display: none; }
    .fit-label { font-size: .75rem; color: var(--muted); cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 5px; }
    .fit-label:hover { color: var(--green); }
    .fit-info { display: flex; align-items: center; justify-content: space-between; gap: 4px; margin-top: 4px; }
    .fit-filename { font-size: .72rem; color: var(--green); font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100px; }
    .fit-remove { background: none; border: none; cursor: pointer; color: #c62828; font-size: .8rem; padding: 0; }
    .rest-badge { text-align: center; padding: 22px 8px; color: var(--muted); font-size: .85rem; }
    .rest-badge .icon { font-size: 2rem; display: block; margin-bottom: 4px; }
    .tipo-badge { border-radius: 6px; padding: 6px 10px; font-size: .82rem; font-weight: 700; color: #fff; text-align: center; }
    .metrics { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; }
    .metric  { background: #f5f5f5; border-radius: 6px; padding: 5px 8px; text-align: center; }
    .metric .mv { font-size: .85rem; font-weight: 700; color: var(--text); }
    .metric .ml { font-size: .65rem; color: var(--muted); text-transform: uppercase; letter-spacing: .4px; margin-top: 1px; }
    .treino-resumo { list-style: none; background: #f7f9fc; border-radius: 8px; padding: 8px 10px; margin-bottom: 2px; }
    .treino-resumo li { font-size: .8rem; color: var(--text); padding: 3px 0; display: flex; align-items: center; gap: 6px; border-bottom: 1px solid #eee; }
    .treino-resumo li:last-child { border-bottom: none; }
    .treino-resumo li .ri { font-size: .85rem; width: 16px; text-align: center; }
    .treino-resumo li .rk { color: var(--muted); font-size: .72rem; font-weight: 600; text-transform: uppercase; letter-spacing: .4px; min-width: 58px; }
    .treino-resumo li .rv { font-weight: 700; }
    .rest-toggle { background: none; border: none; color: var(--muted); font-size: .72rem; cursor: pointer; text-decoration: underline; padding: 2px 0; width: 100%; text-align: center; }
    .rest-toggle:hover { color: var(--text); }

    .resultado-section { border-top: 2px solid var(--green); margin-top: 10px; padding-top: 10px; }
    .resultado-header { font-size: .75rem; font-weight: 700; text-transform: uppercase; letter-spacing: .7px; color: var(--green); margin-bottom: 8px; display: flex; align-items: center; gap: 5px; }
    .analise-bloco { background: #f7f9fc; border-radius: 8px; padding: 8px 10px; margin-top: 6px; }
    .analise-bloco .resumo-txt { font-size: .8rem; color: var(--text); font-style: italic; margin-bottom: 6px; line-height: 1.4; }
    .analise-lista { list-style: none; }
    .analise-lista li { font-size: .78rem; padding: 2px 0; display: flex; gap: 6px; align-items: flex-start; }
    .analise-lista li .icon { flex-shrink: 0; }

    .tipo-Z2_LONGO    { background: #1565c0; }
    .tipo-TIROS       { background: #c62828; }
    .tipo-VO2MAX      { background: #6a1b9a; }
    .tipo-TEMPO       { background: #e65100; }
    .tipo-FORCA       { background: #5d4037; }
    .tipo-RECUPERACAO { background: #00695c; }
    .tipo-DESCANSO    { background: #607d8b; }

    .actions { display: flex; gap: 12px; flex-wrap: wrap; }
    .btn { padding: 13px 22px; border: none; border-radius: 10px; font-size: .95rem; font-weight: 700; cursor: pointer; transition: all .2s; display: flex; align-items: center; gap: 6px; }
    .btn-save  { background: var(--green);  color: #fff; flex: 1; justify-content: center; }
    .btn-save:hover:not(:disabled)  { background: #0e7166; }
    .btn-test  { background: var(--green2); color: #fff; }
    .btn-test:hover:not(:disabled)  { background: #1da851; }
    .btn-sec   { background: #fff; color: var(--text); border: 1.5px solid var(--border); }
    .btn-sec:hover:not(:disabled)   { border-color: var(--green); color: var(--green); }
    .btn:disabled { opacity: .5; cursor: not-allowed; }

    .spinner { width: 16px; height: 16px; border: 2px solid rgba(255,255,255,.4); border-top-color: #fff; border-radius: 50%; animation: spin .7s linear infinite; }
    @keyframes spin { to { transform: rotate(360deg); } }

    .toast { position: fixed; bottom: 28px; left: 50%; transform: translateX(-50%); padding: 12px 28px; border-radius: 10px; font-size: .9rem; font-weight: 600; z-index: 9999; opacity: 0; pointer-events: none; transition: opacity .3s; white-space: nowrap; }
    .toast.show { opacity: 1; }
    .toast.ok  { background: #2e7d32; color: #fff; }
    .toast.err { background: #c62828; color: #fff; }
    .toast.info{ background: #323232; color: #fff; }
  </style>
</head>
<body>

<nav>
  <span style="font-size:1.7rem">🚵</span>
  <div>
    <div class="logo">MTB Nutrition</div>
    <div class="sub">Portal de Treinos</div>
  </div>
  <div class="nav-links">
    <a href="/whatsapp/">📲 WhatsApp</a>
    <a href="/docs">📖 API Docs</a>
  </div>
</nav>

<main>
  <div class="week-bar">
    <button class="arrow" onclick="changeWeek(-1)">&#8592;</button>
    <div class="week-label" id="weekLabel"></div>
    <button class="today-btn" onclick="goToday()">Hoje</button>
    <button class="arrow" onclick="changeWeek(1)">&#8594;</button>
  </div>

  <div class="card">
    <div class="section-label">💡 Objetivo / Foco da Semana</div>
    <textarea id="objetivo" placeholder="Ex: Semana de base aeróbica com 2 sessões de Z2 longo. Foco em manter FC abaixo de 153 bpm. Volume total: ~12h de pedal..."></textarea>
  </div>

  <div class="section-label" style="margin-bottom:12px">📅 Treinos da Semana</div>
  <div class="days-grid" id="daysGrid"></div>

  <div class="actions">
    <button class="btn btn-save" id="btnSave" onclick="salvar()">💾 Salvar Semana</button>
    <button class="btn btn-sec"  id="btnGarmin" onclick="sincronizarGarmin()">🔄 Sincronizar Garmin</button>
    <button class="btn btn-test" id="btnTest" onclick="testar()">📲 Testar WhatsApp</button>
    <button class="btn btn-sec"  onclick="location.href='/whatsapp/'">✏️ Mensagem Manual</button>
  </div>
</main>

<div class="toast" id="toast"></div>

<script>
const DIAS  = ['Segunda','Terça','Quarta','Quinta','Sexta','Sábado','Domingo'];
const TIPOS = [
  {v:'DESCANSO',    l:'🛌 Descanso',    s:'Descanso'},
  {v:'Z2_LONGO',   l:'🚴 Z2 Longo',    s:'Z2 Longo'},
  {v:'TIROS',      l:'⚡ Tiros',        s:'Tiros'},
  {v:'VO2MAX',     l:'🔥 VO2Max',       s:'VO2Max'},
  {v:'TEMPO',      l:'💨 Tempo',        s:'Tempo'},
  {v:'FORCA',      l:'💪 Força',        s:'Força'},
  {v:'RECUPERACAO',l:'🌿 Recuperação',  s:'Recuperação'},
];

let monday = getMonday(new Date());

function getMonday(d) {
  const day = d.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  const m = new Date(d);
  m.setDate(d.getDate() + diff);
  m.setHours(0,0,0,0);
  return m;
}

function addDays(d, n) { const r = new Date(d); r.setDate(r.getDate() + n); return r; }

function fmt(d) { return d.toLocaleDateString('pt-BR', {day:'2-digit', month:'2-digit'}); }

function iso(d) { return d.toISOString().split('T')[0]; }

function updateLabel() {
  document.getElementById('weekLabel').textContent = fmt(monday) + ' — ' + fmt(addDays(monday, 6));
}

function changeWeek(n) { monday = addDays(monday, n * 7); load(); }
function goToday()     { monday = getMonday(new Date()); load(); }

function buildCards(treinos) {
  const grid = document.getElementById('daysGrid');
  grid.innerHTML = '';
  const map = {};
  (treinos||[]).forEach(t => { map[t.data] = t; });
  const todayISO = iso(new Date());

  for (let i = 0; i < 7; i++) {
    const d   = addDays(monday, i);
    const key = iso(d);
    const t   = map[key] || {data: key, tipo:'DESCANSO'};
    const isToday = key === todayISO;

    const c = document.createElement('div');
    c.className = 'day-card' + (isToday ? ' today' : '');

    const opts = TIPOS.map(tp =>
      `<option value="${tp.v}" ${tp.v===t.tipo?'selected':''}>${tp.s}</option>`
    ).join('');

    const dur     = t.duracao_min   || '';
    const dist    = t.distancia_km  || '';
    const elev    = t.elevacao_m    || '';
    const cad     = t.cadencia_rpm  || '';
    const desc    = t.descricao     || '';
    const fitFile = t.fit_file      || '';
    const hide    = t.tipo === 'DESCANSO';
    const tipoLbl = (TIPOS.find(tp => tp.v === t.tipo) || {l: t.tipo}).l;

    const res = t.resultado || null;
    const resHTML = (() => {
      if (!res) return '';
      const ia = res.analise_ia || {};
      const fortes = (ia.pontos_fortes || []).map(p => `<li><span class="icon">✅</span>${p}</li>`).join('');
      const fracos = (ia.pontos_fracos || []).map(p => `<li><span class="icon">⚠️</span>${p}</li>`).join('');
      const resumoTxt = ia.resumo ? `<div class="resumo-txt">"${ia.resumo}"</div>` : '';
      const mItems = [];
      if (res.duracao_min) { const h=Math.floor(res.duracao_min/60),m=res.duracao_min%60; mItems.push(`<div class="metric"><div class="mv">${h>0?h+'h':''}${m>0?m+'min':''}</div><div class="ml">Real</div></div>`); }
      if (res.distancia_km) mItems.push(`<div class="metric"><div class="mv">${res.distancia_km} km</div><div class="ml">Distância</div></div>`);
      if (res.avg_hr) mItems.push(`<div class="metric"><div class="mv">${res.avg_hr} bpm</div><div class="ml">FC média</div></div>`);
      if (res.max_hr) mItems.push(`<div class="metric"><div class="mv">${res.max_hr} bpm</div><div class="ml">FC máx</div></div>`);
      if (res.calorias) mItems.push(`<div class="metric"><div class="mv">${res.calorias}</div><div class="ml">kcal</div></div>`);
      return `<div class="resultado-section">
        <div class="resultado-header">📊 Resultado</div>
        ${mItems.length ? `<div class="metrics">${mItems.join('')}</div>` : ''}
        <div class="analise-bloco">
          ${resumoTxt}
          ${fortes ? `<ul class="analise-lista">${fortes}</ul>` : ''}
          ${fracos  ? `<ul class="analise-lista" style="margin-top:4px">${fracos}</ul>` : ''}
        </div>
      </div>`;
    })();

    const fitInfoHTML = fitFile
      ? `<div class="fit-info">
           <a class="fit-filename" href="/workout/fit/${iso(monday)}/${key}" title="${fitFile}" download>${fitFile}</a>
           <button class="fit-remove" onclick="removerFit('${key}')" title="Remover">✕</button>
         </div>`
      : '';

    const metricsHTML = (dur || dist || elev)
      ? `<div class="metrics" id="metrics-${key}">
           ${dur  ? `<div class="metric"><div class="mv">${dur} min</div><div class="ml">Duração</div></div>` : ''}
           ${dist ? `<div class="metric"><div class="mv">${dist} km</div><div class="ml">Distância</div></div>` : ''}
           ${elev ? `<div class="metric"><div class="mv">${elev} m</div><div class="ml">Elevação</div></div>` : ''}
         </div>`
      : `<div id="metrics-${key}"></div>`;

    const durStr = dur ? (() => { const h = Math.floor(dur/60); const m = dur%60; return (h>0?h+'h':'')+( m>0?m+'min':''); })() : '';
    const resumoHTML = !hide ? `
      <ul class="treino-resumo" id="resumo-${key}">
        <li><span class="ri">⏱</span><span class="rk">Tempo</span><span class="rv" id="resumo-dur-${key}">${durStr || '—'}</span></li>
        <li><span class="ri">🦵</span><span class="rk">Cadência</span><span class="rv" id="resumo-cad-${key}">${cad ? cad+' rpm' : '—'}</span></li>
      </ul>` : '';

    c.innerHTML = `
      <div class="day-head tipo-${t.tipo}" id="h-${key}">
        <div class="day-name">${DIAS[i]}${isToday ? ' ●' : ''}</div>
        <div class="day-date">${fmt(d)}</div>
      </div>
      <div class="day-body">
        <input type="hidden" id="dur-${key}"     value="${dur}">
        <input type="hidden" id="dist-${key}"    value="${dist}">
        <input type="hidden" id="elev-${key}"    value="${elev}">
        <input type="hidden" id="cad-${key}"     value="${cad}">
        <input type="hidden" id="fitfile-${key}" value="${fitFile}">
        <select id="tp-${key}" style="${hide ? 'display:none' : ''}" onchange="onTipo('${key}')">
          ${opts}
        </select>

        <div id="ex-${key}" style="${hide ? 'display:none' : ''}">
          ${resumoHTML}
          ${metricsHTML}

          <div class="fit-area">
            <label class="fit-label" for="fit-${key}">📎 Enviar arquivo .fit</label>
            <input type="file" id="fit-${key}" accept=".fit" onchange="uploadFit('${key}', this)">
            <div id="fitinfo-${key}">${fitInfoHTML}</div>
          </div>
          <div>
            <label>Notas</label>
            <textarea id="desc-${key}" placeholder="Detalhes...">${desc}</textarea>
          </div>
        </div>

        <div id="rest-${key}" style="${hide ? '' : 'display:none'}">
          <div class="rest-badge"><span class="icon">😴</span>Dia de descanso</div>
        </div>
        <button class="rest-toggle" id="resttoggle-${key}" onclick="toggleRest('${key}')">
          ${hide ? '🏃 Adicionar treino' : '🛌 Marcar descanso'}
        </button>
        ${resHTML}
      </div>`;
    grid.appendChild(c);
  }
}

function atualizarResumo(key) {
  const tipo = document.getElementById(`tp-${key}`)?.value || 'DESCANSO';
  const tipoLbl = (TIPOS.find(tp => tp.v === tipo) || {l: tipo}).l;
  const dur  = parseInt(document.getElementById(`dur-${key}`)?.value || '0') || 0;
  const cad  = document.getElementById(`cad-${key}`)?.value?.trim() || '';
  const durStr = dur ? (() => { const h = Math.floor(dur/60); const m = dur%60; return (h>0?h+'h':'')+( m>0?m+'min':''); })() : '—';
  const tipoEl = document.getElementById(`resumo-tipo-${key}`);
  const durEl  = document.getElementById(`resumo-dur-${key}`);
  const cadEl  = document.getElementById(`resumo-cad-${key}`);
  if (tipoEl) tipoEl.textContent = tipoLbl;
  if (durEl)  durEl.textContent  = durStr;
  if (cadEl)  cadEl.textContent  = cad ? cad + ' rpm' : '—';
}

function onTipo(key) {
  const tipo = document.getElementById(`tp-${key}`).value;
  document.getElementById(`h-${key}`).className = `day-head tipo-${tipo}`;
  const hide = tipo === 'DESCANSO';
  const sel = document.getElementById(`tp-${key}`);
  if (sel) sel.style.display = hide ? 'none' : '';
  document.getElementById(`ex-${key}`).style.display   = hide ? 'none' : '';
  document.getElementById(`rest-${key}`).style.display = hide ? '' : 'none';
  const toggle = document.getElementById(`resttoggle-${key}`);
  if (toggle) toggle.textContent = hide ? '🏃 Adicionar treino' : '🛌 Marcar descanso';
  atualizarResumo(key);
}

function toggleRest(key) {
  const sel = document.getElementById(`tp-${key}`);
  sel.value = sel.value === 'DESCANSO' ? 'Z2_LONGO' : 'DESCANSO';
  onTipo(key);
}

function collect() {
  const treinos = [];
  for (let i = 0; i < 7; i++) {
    const key  = iso(addDays(monday, i));
    const tipo = document.getElementById(`tp-${key}`).value;
    const t    = {data: key, tipo};
    if (tipo !== 'DESCANSO') {
      const dur     = document.getElementById(`dur-${key}`)?.value     || '';
      const dist    = document.getElementById(`dist-${key}`)?.value    || '';
      const elev    = document.getElementById(`elev-${key}`)?.value    || '';
      const cad     = document.getElementById(`cad-${key}`)?.value     || '';
      const desc    = document.getElementById(`desc-${key}`)?.value    || '';
      const fitfile = document.getElementById(`fitfile-${key}`)?.value || '';
      if (dur)     t.duracao_min  = parseInt(dur);
      if (dist)    t.distancia_km = parseFloat(dist);
      if (elev)    t.elevacao_m   = parseFloat(elev);
      if (cad)     t.cadencia_rpm = cad.trim();
      if (desc)    t.descricao    = desc.trim();
      if (fitfile) t.fit_file     = fitfile;
    }
    treinos.push(t);
  }
  return treinos;
}

async function load() {
  updateLabel();
  try {
    const r = await fetch(`/workout/semana/${iso(monday)}`);
    const d = await r.json();
    document.getElementById('objetivo').value = d.objetivo || '';
    buildCards(d.treinos || []);
  } catch {
    buildCards([]);
  }
}

async function salvar() {
  const btn = document.getElementById('btnSave');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Salvando...';
  try {
    const r = await fetch('/workout/semana', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        semana_inicio: iso(monday),
        objetivo: document.getElementById('objetivo').value.trim(),
        treinos: collect(),
      }),
    });
    if (!r.ok) throw new Error(await r.text());
    toast('✅ Semana salva!', 'ok');
  } catch(e) {
    toast('❌ Erro: ' + e.message, 'err');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '💾 Salvar Semana';
  }
}

async function testar() {
  const btn = document.getElementById('btnTest');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Enviando...';
  try {
    const r = await fetch('/whatsapp/teste', {method:'POST'});
    const d = await r.json();
    if (r.ok) toast('📲 Mensagem de teste enviada!', 'ok');
    else throw new Error(d.detail || JSON.stringify(d));
  } catch(e) {
    toast('❌ ' + e.message, 'err');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '📲 Testar WhatsApp';
  }
}

async function uploadFit(key, input) {
  if (!input.files || !input.files[0]) return;
  const file = input.files[0];
  if (!file.name.toLowerCase().endsWith('.fit')) {
    toast('❌ Apenas arquivos .fit são permitidos', 'err');
    input.value = '';
    return;
  }
  const semana = iso(monday);
  const form = new FormData();
  form.append('arquivo', file);
  toast('⏳ Analisando treino...', 'info');
  try {
    const r = await fetch(`/workout/fit/${semana}/${key}`, {method: 'POST', body: form});
    if (!r.ok) throw new Error(await r.text());
    const d = await r.json();

    // atualiza select oculto, cabeçalho e badge
    const tipo = d.tipo || 'Z2_LONGO';
    const sel = document.getElementById(`tp-${key}`);
    if (sel) { sel.value = tipo; onTipo(key); }

    // salva referência do arquivo nos hiddens
    const ffEl = document.getElementById(`fitfile-${key}`);
    if (ffEl && d.fit_file) ffEl.value = d.fit_file;
    if (d.duracao_min)   { const el = document.getElementById(`dur-${key}`);  if (el) el.value = d.duracao_min; }
    if (d.distancia_km)  { const el = document.getElementById(`dist-${key}`); if (el) el.value = d.distancia_km; }
    if (d.elevacao_m)    { const el = document.getElementById(`elev-${key}`); if (el) el.value = d.elevacao_m; }
    if (d.cadencia_rpm)  { const el = document.getElementById(`cad-${key}`);  if (el) { el.value = d.cadencia_rpm; atualizarResumo(key); } }

    // link do arquivo
    document.getElementById(`fitinfo-${key}`).innerHTML =
      `<div class="fit-info">
         <a class="fit-filename" href="/workout/fit/${semana}/${key}" title="${d.fit_file}" download>${d.fit_file}</a>
         <button class="fit-remove" onclick="removerFit('${key}')" title="Remover">✕</button>
       </div>`;

    // métricas em cards
    const metrics = document.getElementById(`metrics-${key}`);
    if (metrics) {
      const items = [];
      if (d.duracao_min)  items.push(`<div class="metric"><div class="mv">${d.duracao_min} min</div><div class="ml">Duração</div></div>`);
      if (d.distancia_km) items.push(`<div class="metric"><div class="mv">${d.distancia_km} km</div><div class="ml">Distância</div></div>`);
      if (d.elevacao_m)   items.push(`<div class="metric"><div class="mv">${d.elevacao_m} m</div><div class="ml">Elevação</div></div>`);
      if (d.avg_hr)       items.push(`<div class="metric"><div class="mv">${d.avg_hr} bpm</div><div class="ml">FC média</div></div>`);
      if (d.max_hr)       items.push(`<div class="metric"><div class="mv">${d.max_hr} bpm</div><div class="ml">FC máx</div></div>`);
      if (d.calorias)     items.push(`<div class="metric"><div class="mv">${d.calorias}</div><div class="ml">Calorias</div></div>`);
      metrics.className = items.length ? 'metrics' : '';
      metrics.innerHTML = items.join('');
    }

    // preenche descrição automática se o campo estiver vazio
    const descEl = document.getElementById(`desc-${key}`);
    if (descEl && !descEl.value.trim()) {
      // usa notas do workout do Garmin se disponível
      if (d.workout_notes) {
        descEl.value = d.workout_notes;
      } else {
      const TIPO_LABELS = {
        Z2_LONGO: 'Z2 Longo', TIROS: 'Tiros', VO2MAX: 'VO2Max',
        TEMPO: 'Tempo', FORCA: 'Força', RECUPERACAO: 'Recuperação', DESCANSO: 'Descanso',
      };
      const linhas = [];
      linhas.push(TIPO_LABELS[tipo] || tipo);
      if (d.duracao_min) {
        const h = Math.floor(d.duracao_min / 60);
        const m = d.duracao_min % 60;
        linhas.push(`Tempo: ${h > 0 ? h + 'h' : ''}${m > 0 ? m + 'min' : ''}`);
      }
      if (d.distancia_km) linhas.push(`Distância: ${d.distancia_km} km`);
      if (d.elevacao_m)   linhas.push(`Elevação: ${d.elevacao_m} m`);
      if (d.avg_hr)       linhas.push(`FC média: ${d.avg_hr} bpm`);
      if (d.calorias)     linhas.push(`Calorias: ${d.calorias}`);
      descEl.value = linhas.join('\\n');
      } // fim else workout_notes
    }

    const lbl = (TIPOS.find(tp => tp.v === tipo) || {l: tipo}).l;
    toast(`✅ ${lbl} detectado`, 'ok');
  } catch(e) {
    toast('❌ Erro ao enviar: ' + e.message, 'err');
  } finally {
    input.value = '';
  }
}

async function removerFit(key) {
  const semana = iso(monday);
  try {
    const r = await fetch(`/workout/fit/${semana}/${key}`, {method: 'DELETE'});
    if (!r.ok) throw new Error(await r.text());

    // limpa arquivo e hidden inputs de métricas
    document.getElementById(`fitinfo-${key}`).innerHTML = '';
    ['dur','dist','elev','fitfile'].forEach(f => {
      const el = document.getElementById(`${f}-${key}`);
      if (el) el.value = '';
    });

    // limpa cadência e notas
    const cadEl = document.getElementById(`cad-${key}`);
    if (cadEl) cadEl.value = '';
    const descEl = document.getElementById(`desc-${key}`);
    if (descEl) descEl.value = '';

    // reseta o card para DESCANSO
    const sel = document.getElementById(`tp-${key}`);
    if (sel) { sel.value = 'DESCANSO'; onTipo(key); }

    // limpa métricas
    const metrics = document.getElementById(`metrics-${key}`);
    if (metrics) { metrics.className = ''; metrics.innerHTML = ''; }

    toast('🗑️ Arquivo removido', 'info');
  } catch(e) {
    toast('❌ Erro ao remover: ' + e.message, 'err');
  }
}

async function sincronizarGarmin() {
  const btn = document.getElementById('btnGarmin');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner" style="border-color:rgba(0,0,0,.2);border-top-color:#333"></span> Sincronizando...';
  try {
    const r = await fetch(`/workout/garmin/sync/${iso(monday)}`, {method: 'POST'});
    if (!r.ok) throw new Error(await r.text());
    const d = await r.json();
    const msg = `✅ Garmin: ${d.treinos_importados} treino(s) · ${d.atividades_processadas} atividade(s)`;
    toast(msg, 'ok');
    await load();
  } catch(e) {
    toast('❌ Garmin: ' + e.message, 'err');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '🔄 Sincronizar Garmin';
  }
}

let _tt;
function toast(msg, type='info') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className   = 'toast show ' + type;
  clearTimeout(_tt);
  _tt = setTimeout(() => { el.className = 'toast'; }, 3500);
}

load();
</script>
</body>
</html>"""


@router.get("/", response_class=HTMLResponse)
async def portal():
    return HTML
