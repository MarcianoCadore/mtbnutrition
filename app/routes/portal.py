from fastapi import APIRouter, Request
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
    nav .nav-toggle { display: none; margin-left: auto; background: rgba(255,255,255,.15); border: none; color: #fff; font-size: 1.4rem; line-height: 1; width: 42px; height: 42px; border-radius: 8px; cursor: pointer; }
    nav .nav-user { color: rgba(255,255,255,.75); font-size: 0.85rem; font-weight: 600; white-space: nowrap; }

    main { max-width: 1400px; margin: 0 auto; padding: 24px 20px 80px; }

    .week-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 24px; flex-wrap: wrap; }
    .week-bar .arrow { background: #fff; border: 1.5px solid var(--border); border-radius: 8px; width: 38px; height: 38px; cursor: pointer; font-size: 1.1rem; display: flex; align-items: center; justify-content: center; transition: all .15s; }
    .week-bar .arrow:hover { border-color: var(--green); color: var(--green); }
    .week-label { font-size: 1.05rem; font-weight: 700; flex: 1; text-align: center; }
    .today-btn { background: none; border: none; color: var(--green); font-size: 0.85rem; text-decoration: underline; cursor: pointer; }

    .card { background: #fff; border-radius: 12px; padding: 20px; margin-bottom: 20px; box-shadow: 0 1px 4px rgba(0,0,0,.08); }

    .prova-panel { background: linear-gradient(135deg, #0e8a7d, #128c7e); color: #fff; border-radius: 12px; padding: 18px 20px; margin-bottom: 20px; box-shadow: 0 2px 10px rgba(14,138,125,.3); }
    .prova-panel .pp-top { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    .prova-panel .pp-label { font-size: .7rem; font-weight: 700; text-transform: uppercase; letter-spacing: .8px; opacity: .85; }
    .prova-panel .pp-nome { font-size: 1.15rem; font-weight: 800; }
    .prova-panel .pp-fase { margin-left: auto; background: rgba(255,255,255,.2); border-radius: 20px; padding: 4px 12px; font-size: .75rem; font-weight: 700; white-space: nowrap; }
    .prova-panel .pp-sub { font-size: .85rem; opacity: .92; margin-top: 3px; }
    .prova-panel .pp-count { font-size: 1.4rem; font-weight: 800; margin: 8px 0 2px; }
    .prova-panel .pp-focos { background: rgba(255,255,255,.13); border-radius: 10px; padding: 10px 12px; margin-top: 12px; }
    .prova-panel .pp-focos .pf-titulo { font-size: .72rem; font-weight: 700; text-transform: uppercase; letter-spacing: .6px; opacity: .9; margin-bottom: 6px; }
    .prova-panel .pp-focos ul { list-style: none; }
    .prova-panel .pp-focos li { font-size: .85rem; padding: 3px 0; display: flex; gap: 7px; align-items: flex-start; line-height: 1.35; }
    .prova-panel a.pp-link { color: #fff; text-decoration: underline; font-size: .82rem; opacity: .9; }
    .prova-cta { background: #fff; border: 1.5px dashed var(--green); border-radius: 12px; padding: 14px 18px; margin-bottom: 20px; text-align: center; }
    .prova-cta a { color: var(--green); font-weight: 700; text-decoration: none; font-size: .92rem; }
    .section-label { font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: .8px; color: var(--muted); margin-bottom: 8px; }
    .card textarea { width: 100%; border: 1.5px solid var(--border); border-radius: 8px; padding: 10px 12px; font-size: .95rem; font-family: inherit; resize: vertical; min-height: 72px; outline: none; transition: border-color .2s; line-height: 1.5; }
    .card textarea:focus { border-color: var(--green); }

    .days-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 10px; margin-bottom: 24px; }
    @media(max-width:1000px){ .days-grid { grid-template-columns: repeat(4,1fr); } }
    @media(max-width:760px) { .days-grid { grid-template-columns: repeat(2,1fr); } }
    @media(max-width:560px) { .days-grid { grid-template-columns: 1fr; } }

    .day-card { background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,.08); transition: box-shadow .2s; }
    .day-card:hover { box-shadow: 0 4px 14px rgba(0,0,0,.13); }
    .day-card.today { outline: 2.5px solid var(--green); }
    .day-card.realizado { background: #d9f7e1; }
    .day-card.realizado .day-body { background: #d9f7e1; }
    .day-card.perdido { background: #ffe2bf; }
    .day-card.perdido .day-body { background: #ffe2bf; }
    .day-card.futuro { opacity: .72; }
    .day-card.futuro .day-body select,
    .day-card.futuro .day-body textarea,
    .day-card.futuro .day-body input[type=file] { pointer-events: none; opacity: .6; }
    .day-card.futuro .rest-toggle,
    .day-card.futuro .fit-label,
    .day-card.futuro .fit-remove { pointer-events: none; opacity: .4; }
    .lock-badge { font-size: .7rem; color: var(--muted); text-align: center; padding: 4px 0 2px; letter-spacing: .02em; }
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
    .periodo-sel { margin-top: 6px; }
    .nutri-ref-obs { margin-top: 6px; font-size: .82rem; font-weight: 600; color: #8a5a00; background: #fff7e6; border-radius: 6px; padding: 6px 9px; }
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
    .treino-resumo li .rv.rv-cad { white-space: nowrap; }
    .rest-toggle { background: none; border: none; color: var(--muted); font-size: .72rem; cursor: pointer; text-decoration: underline; padding: 2px 0; width: 100%; text-align: center; }
    .rest-toggle:hover { color: var(--text); }

    .resultado-section { border-top: 2px solid var(--green); margin-top: 10px; padding-top: 10px; }
    .resultado-header { font-size: .75rem; font-weight: 700; text-transform: uppercase; letter-spacing: .7px; color: var(--green); margin-bottom: 8px; display: flex; align-items: center; gap: 5px; }
    .nota-treino { display: flex; align-items: center; justify-content: center; gap: 10px; background: #f7f9fc; border-radius: 10px; padding: 12px; margin-top: 10px; }
    .nota-treino .nota-num { font-size: 2rem; font-weight: 800; line-height: 1; }
    .nota-treino .nota-de { font-size: .9rem; font-weight: 700; color: var(--muted); }
    .nota-treino .nota-lbl { font-size: .7rem; font-weight: 700; text-transform: uppercase; letter-spacing: .6px; color: var(--muted); }
    .analise-bloco { background: #f7f9fc; border-radius: 8px; padding: 8px 10px; margin-top: 6px; }
    .analise-bloco .resumo-txt { font-size: .8rem; color: var(--text); font-style: italic; margin-bottom: 6px; line-height: 1.4; }
    .analise-lista { list-style: none; }
    .analise-lista li { font-size: .78rem; padding: 2px 0; display: flex; gap: 6px; align-items: flex-start; }
    .analise-lista li .icon { flex-shrink: 0; }
    .aval-btn { margin-top: 8px; background: #eef4ff; border: 1px solid #cfe0ff; color: #1565c0; font-size: .8rem; font-weight: 700; cursor: pointer; padding: 9px 10px; border-radius: 8px; width: 100%; }
    .aval-btn:hover { background: #e2edff; }

    .nutri-area { margin-top: 8px; border-top: 1px dashed var(--border); padding-top: 8px; }
    .nutri-toggle { background: #f1f8f6; border: 1px solid #cfe9e3; color: var(--green); font-size: .8rem; font-weight: 700; cursor: pointer; padding: 8px 10px; border-radius: 8px; width: 100%; display: flex; align-items: center; justify-content: center; gap: 6px; }
    .nutri-toggle:hover { background: #e6f3ef; }
    .nutri-estrat { font-size: .76rem; color: var(--muted); font-style: italic; background: #f7f9fc; border-radius: 8px; padding: 7px 9px; margin-bottom: 8px; line-height: 1.4; }
    .nutri-prova { background: #e8f8ec; border: 1px solid #b6e6c4; border-radius: 10px; padding: 11px 13px; margin-bottom: 10px; }
    .nutri-prova .np-tit { font-size: .85rem; font-weight: 800; color: #1e7a44; margin-bottom: 6px; }
    .nutri-prova ul { list-style: none; margin: 0; padding: 0; }
    .nutri-prova li { font-size: .8rem; color: var(--text); padding: 3px 0 3px 16px; position: relative; line-height: 1.35; }
    .nutri-prova li::before { content: "•"; position: absolute; left: 3px; color: #1e7a44; font-weight: 700; }
    .nutri-meta { display: flex; gap: 8px; margin-bottom: 8px; }
    .nutri-meta .nm { flex: 1; background: var(--green); color: #fff; border-radius: 8px; padding: 6px; text-align: center; }
    .nutri-meta .nm .nmv { font-size: .95rem; font-weight: 800; }
    .nutri-meta .nm .nml { font-size: .62rem; text-transform: uppercase; letter-spacing: .4px; opacity: .9; }
    .nutri-ref { border-bottom: 1px solid #eee; padding: 6px 0; }
    .nutri-ref:last-child { border-bottom: none; }
    .nutri-ref-h { display: flex; justify-content: space-between; align-items: baseline; gap: 6px; }
    .nutri-ref-h .nrn { font-size: .78rem; font-weight: 700; }
    .nutri-ref-h .nrt { font-size: .68rem; color: var(--muted); font-weight: 600; white-space: nowrap; }
    .nutri-ref ul { list-style: none; margin-top: 3px; }
    .nutri-ref li { display: flex; justify-content: space-between; gap: 8px; font-size: .76rem; padding: 2px 0; }
    .nutri-ref li .nk { color: var(--muted); font-size: .7rem; white-space: nowrap; }

    .modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.5); display: none; align-items: center; justify-content: center; z-index: 100; padding: 16px; }
    .modal-overlay.show { display: flex; }
    .modal { background: #fff; border-radius: 16px; max-width: 460px; width: 100%; max-height: 86vh; overflow-y: auto; position: relative; padding: 22px; box-shadow: 0 10px 40px rgba(0,0,0,.25); }
    .modal-close { position: absolute; top: 12px; right: 12px; background: #f0f2f5; border: none; width: 30px; height: 30px; border-radius: 50%; cursor: pointer; font-size: 1rem; color: var(--muted); line-height: 1; }
    .modal-close:hover { background: #e5e7eb; }
    .modal-head h3 { font-size: 1.1rem; color: var(--green); }
    .modal-head .modal-sub { font-size: .82rem; color: var(--muted); font-weight: 600; margin-bottom: 12px; }

    .notas-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
    .info-treino { background: none; border: none; color: var(--green); font-size: .72rem; font-weight: 600; cursor: pointer; padding: 0; display: inline-flex; align-items: center; gap: 3px; opacity: .8; transition: opacity .15s; }
    .info-treino:hover { opacity: 1; text-decoration: underline; }
    .info-treino .ic { font-size: .82rem; }
    .esp-obj { font-size: .86rem; color: var(--text); line-height: 1.45; margin-bottom: 14px; }
    .esp-bloco { margin-bottom: 14px; }
    .esp-titulo { font-size: .7rem; text-transform: uppercase; letter-spacing: .5px; color: var(--muted); font-weight: 700; margin-bottom: 6px; }
    .esp-lista { list-style: none; }
    .esp-lista li { font-size: .84rem; padding: 6px 10px; background: #f7f9fc; border-radius: 7px; margin-bottom: 5px; line-height: 1.35; }
    .esp-dica { font-size: .82rem; color: #8a5a00; background: #fff7e6; border-radius: 8px; padding: 10px 12px; line-height: 1.4; }
    .esp-notas { font-size: .82rem; color: var(--text); line-height: 1.45; background: #f7f9fc; border-radius: 8px; padding: 10px 12px; }

    .gen-modal-treino { background: #f7f9fc; border-radius: 8px; padding: 10px 12px; margin-bottom: 8px; }
    .gen-modal-treino .gmt-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 4px; }
    .gen-modal-treino .gmt-data { font-size: .72rem; color: var(--muted); font-weight: 600; }
    .gen-modal-treino .gmt-tipo { font-size: .8rem; font-weight: 700; color: #fff; padding: 3px 8px; border-radius: 5px; }
    .gen-modal-treino .gmt-dur  { font-size: .75rem; color: var(--muted); }
    .gen-modal-treino .gmt-desc { font-size: .78rem; color: var(--text); line-height: 1.4; }
    .gen-analise { font-size: .82rem; font-style: italic; color: #555; background: #fff7e6; border-radius: 8px; padding: 10px 12px; margin-bottom: 14px; line-height: 1.45; }
    .gen-prog    { font-size: .8rem; color: var(--green); background: #eef9f5; border-radius: 8px; padding: 8px 12px; margin-bottom: 14px; }
    .btn-enviar  { background: #2e7d32; color: #fff; border: none; border-radius: 10px; padding: 13px 20px; font-size: .95rem; font-weight: 700; cursor: pointer; width: 100%; margin-top: 12px; display: flex; align-items: center; justify-content: center; gap: 8px; }
    .btn-enviar:hover:not(:disabled) { background: #1b5e20; }
    .btn-enviar:disabled { opacity: .55; cursor: not-allowed; }

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

    /* Ajustes para celular */
    @media(max-width:640px) {
      nav { flex-wrap: wrap; padding: 12px 16px; gap: 8px; }
      nav .nav-toggle { display: block; }
      nav .nav-links {
        display: none; width: 100%; flex-direction: column; gap: 0;
        margin-left: 0; margin-top: 8px;
      }
      nav.open .nav-links { display: flex; }
      nav .nav-links a {
        font-size: 1rem; opacity: 1; padding: 13px 6px;
        border-top: 1px solid rgba(255,255,255,.18);
      }
      main { padding: 16px 12px 80px; }
      .card { padding: 16px; }
      .week-label { font-size: .95rem; }
      .toast { white-space: normal; max-width: 90vw; text-align: center; }
    }
  </style>
</head>
<body>

<nav>
  <span style="font-size:1.7rem">🚵</span>
  <div>
    <div class="logo">MTB Nutrition</div>
    <div class="sub">Portal de Treinos</div>
  </div>
  <button class="nav-toggle" aria-label="Abrir menu" onclick="this.closest('nav').classList.toggle('open')">☰</button>
  <div class="nav-links">
    {{NAV_NUTRI}}
    <a href="/workout/calendario">📅 Provas</a>
    <a href="/workout/perfil">👤 Perfil</a>
    <a href="/workout/zonas">❤️ Zonas FC</a>
    <a href="/workout/integracao">⌚ Conectar dispositivo</a>
    {{NAV_USER}}
    <a href="/logout">🚪 Sair</a>
  </div>
</nav>

<main>
  <div class="week-bar">
    <button class="arrow" onclick="changeWeek(-1)">&#8592;</button>
    <div class="week-label" id="weekLabel"></div>
    <button class="today-btn" onclick="goToday()">Hoje</button>
    <button class="arrow" onclick="changeWeek(1)">&#8594;</button>
  </div>

  <div id="provaPanel"></div>

  <div class="card">
    <div class="section-label">💡 Objetivo / Foco da Semana</div>
    <textarea id="objetivo" placeholder="Ex: Semana de base aeróbica com 2 sessões de Z2 longo. Foco em manter FC abaixo de 153 bpm. Volume total: ~12h de pedal..."></textarea>
  </div>

  <div class="section-label" style="margin-bottom:12px">📅 Treinos da Semana</div>
  <div class="days-grid" id="daysGrid"></div>

  <div class="actions">
    <button class="btn btn-save" id="btnSave" onclick="salvar()">💾 Salvar Semana</button>
    <button class="btn btn-sec"  id="btnGarmin" onclick="sincronizarGarmin()">🔄 Sincronizar Garmin</button>
    <button class="btn btn-test" id="btnGenSemana" onclick="gerarProximaSemana()">🤖 Gerar próxima semana</button>
  </div>
</main>

<div class="toast" id="toast"></div>

<div class="modal-overlay" id="nutriModal" onclick="fecharNutriModal(event)">
  <div class="modal" onclick="event.stopPropagation()">
    <button class="modal-close" onclick="fecharNutriModal()">✕</button>
    <div class="modal-head" id="nutriModalHead"></div>
    <div class="modal-body" id="nutriModalBody"></div>
  </div>
</div>

<div class="modal-overlay" id="genModal" onclick="fecharGenModal(event)">
  <div class="modal" style="max-width:520px" onclick="event.stopPropagation()">
    <button class="modal-close" onclick="fecharGenModal()">✕</button>
    <div class="modal-head" id="genModalHead"></div>
    <div class="modal-body" id="genModalBody"></div>
  </div>
</div>

<div class="modal-overlay" id="avalModal" onclick="fecharAvalModal(event)">
  <div class="modal" onclick="event.stopPropagation()">
    <button class="modal-close" onclick="fecharAvalModal()">✕</button>
    <div class="modal-head" id="avalModalHead"></div>
    <div class="modal-body" id="avalModalBody"></div>
  </div>
</div>

<div class="modal-overlay" id="treinoModal" onclick="fecharTreinoModal(event)">
  <div class="modal" onclick="event.stopPropagation()">
    <button class="modal-close" onclick="fecharTreinoModal()">✕</button>
    <div class="modal-head" id="treinoModalHead"></div>
    <div class="modal-body" id="treinoModalBody"></div>
  </div>
</div>

<script>
window.NUTRICAO_ON = {{NUTRICAO_ON}};
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
const _resultados = {};
const _planejado = {};

// Especificação de cada tipo de treino — o que está programado e como executar.
const ESPEC_TREINO = {
  Z2_LONGO: {
    obj: 'Base aeróbica. Constrói resistência e melhora a queima de gordura mantendo esforço controlado.',
    estrutura: ['Aquecimento 15 min em Z1', 'Bloco principal contínuo em Z2 (146–158 bpm)', 'Volta à calma 15 min em Z1'],
    dica: 'Cadência 85–95 rpm e FC estável. Sem picos — se subir para Z3, alivie.',
  },
  TEMPO: {
    obj: 'Esforço de limiar. Eleva a capacidade de sustentar um ritmo forte por mais tempo.',
    estrutura: ['Aquecimento 15 min em Z2', '3× [10 min em Z3 (159–165 bpm) + 5 min Z2]', 'Volta à calma 10 min em Z2'],
    dica: 'Esforço moderado-alto sustentável. Respiração ritmada, ainda sob controle.',
  },
  FORCA: {
    obj: 'Força específica. Recruta mais fibras musculares pedalando com cadência baixa e marcha pesada.',
    estrutura: ['Aquecimento 15 min em Z2', '4× [6 min em Z3 com cadência 50–60 rpm + 4 min Z2]', 'Volta à calma 10 min em Z2'],
    dica: 'Marcha pesada, empurre o pedal. Sente o trabalho nas pernas, não no fôlego.',
  },
  TIROS: {
    obj: 'Tiros neuromusculares. Desenvolve potência e velocidade máxima de pedalada.',
    estrutura: ['Aquecimento 15 min em Z2', '8× [30 s máximo em Z5 (>177 bpm) + 3,5 min Z1]', 'Volta à calma 15 min em Z2'],
    dica: 'Cada tiro é all-out, do início ao fim. Recupere bem antes do próximo.',
  },
  VO2MAX: {
    obj: 'VO2max. Eleva o teto cardiorrespiratório — o maior estímulo para a performance.',
    estrutura: ['Aquecimento 15 min em Z2', '4× [4 min forte em Z5 (>177 bpm) + 4 min Z2]', 'Volta à calma 15 min em Z2'],
    dica: 'Os blocos doem. O objetivo é manter a Z5 do primeiro ao último bloco.',
  },
  RECUPERACAO: {
    obj: 'Recuperação ativa. Acelera a regeneração sem gerar fadiga adicional.',
    estrutura: ['Pedal leve e contínuo em Z1 (<145 bpm)'],
    dica: 'Bem leve mesmo. Se a FC subir, reduza o ritmo. É descanso, não treino.',
  },
};

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
function localIso(d) { const y=d.getFullYear(); const m=String(d.getMonth()+1).padStart(2,'0'); const day=String(d.getDate()).padStart(2,'0'); return `${y}-${m}-${day}`; }

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
  const todayISO = localIso(new Date());

  for (let i = 0; i < 7; i++) {
    const d   = addDays(monday, i);
    const key = iso(d);
    const t   = map[key] || {data: key, tipo:'DESCANSO'};
    const isToday = key === todayISO;
    const isRealizado = !!t.resultado;
    const isPerdido = !isRealizado && key < todayISO && t.tipo !== 'DESCANSO';
    const isFuturo = key >= todayISO && !isRealizado;

    const c = document.createElement('div');
    c.className = 'day-card' + (isToday ? ' today' : '') + (isRealizado ? ' realizado' : '') + (isPerdido ? ' perdido' : '') + (isFuturo ? ' futuro' : '');

    const opts = TIPOS.map(tp =>
      `<option value="${tp.v}" ${tp.v===t.tipo?'selected':''}>${tp.s}</option>`
    ).join('');

    const dur     = t.duracao_min   || '';
    const dist    = t.distancia_km  || '';
    const elev    = t.elevacao_m    || '';
    const cad     = t.cadencia_rpm  || '';
    const desc    = t.descricao     || '';
    const fitFile = t.fit_file      || '';
    const periodo = t.periodo       || '';
    const hide    = t.tipo === 'DESCANSO';
    const tipoLbl = (TIPOS.find(tp => tp.v === t.tipo) || {l: t.tipo}).l;
    const lockAttr = isFuturo ? 'disabled' : '';

    _planejado[key] = {tipo: t.tipo, duracao_min: t.duracao_min, cadencia_rpm: t.cadencia_rpm, descricao: t.descricao};
    const res = t.resultado || null;
    if (res) _resultados[key] = res;
    const resHTML = res
      ? `<button class="aval-btn" onclick="abrirAvaliacao('${key}')">📊 Ver avaliação do treino</button>`
      : '';

    const fitInfoHTML = fitFile
      ? `<div class="fit-info">
           <a class="fit-filename" href="/workout/fit/${iso(monday)}/${key}" title="${fitFile}" download>${fitFile}</a>
           <button class="fit-remove" onclick="removerFit('${key}')" title="Remover">✕</button>
         </div>`
      : '';

    const cadReal = (res && res.cadencia_media_rpm) ? res.cadencia_media_rpm : '';
    const metricsHTML = (dur || dist || elev || cadReal)
      ? `<div class="metrics" id="metrics-${key}">
           ${dur  ? `<div class="metric"><div class="mv">${dur} min</div><div class="ml">Duração</div></div>` : ''}
           ${cadReal ? `<div class="metric"><div class="mv">${cadReal} rpm</div><div class="ml">Cad. real</div></div>` : ''}
           ${dist ? `<div class="metric"><div class="mv">${dist} km</div><div class="ml">Distância</div></div>` : ''}
           ${elev ? `<div class="metric"><div class="mv">${elev} m</div><div class="ml">Elevação</div></div>` : ''}
         </div>`
      : `<div id="metrics-${key}"></div>`;

    const durStr = dur ? (() => { const h = Math.floor(dur/60); const m = dur%60; return (h>0?h+'h':'')+( m>0?m+'min':''); })() : '';
    const resumoHTML = !hide ? `
      <ul class="treino-resumo" id="resumo-${key}">
        <li><span class="ri">⏱</span><span class="rk">Tempo</span><span class="rv" id="resumo-dur-${key}">${durStr || '—'}</span></li>
        <li><span class="ri">🦵</span><span class="rk">Cad. alvo</span><span class="rv rv-cad" id="resumo-cad-${key}">${cad ? cad+' rpm' : '—'}</span></li>
      </ul>` : '';

    c.innerHTML = `
      <div class="day-head tipo-${t.tipo}" id="h-${key}">
        <div class="day-name">${DIAS[i]}${isToday ? ' ●' : ''}${isFuturo ? ' 🔒' : ''}</div>
        <div class="day-date">${fmt(d)}</div>
      </div>
      <div class="day-body">
        <input type="hidden" id="dur-${key}"     value="${dur}">
        <input type="hidden" id="dist-${key}"    value="${dist}">
        <input type="hidden" id="elev-${key}"    value="${elev}">
        <input type="hidden" id="cad-${key}"     value="${cad}">
        <input type="hidden" id="fitfile-${key}" value="${fitFile}">
        ${isFuturo ? `<div class="lock-badge">🔒 Treino planejado — edição disponível no dia</div>` : ''}
        <select id="tp-${key}" style="${hide ? 'display:none' : ''}" onchange="onTipo('${key}')" ${lockAttr}>
          ${opts}
        </select>
        <select id="pd-${key}" class="periodo-sel" style="${hide ? 'display:none' : ''}" title="Quando você vai treinar" ${lockAttr}>
          <option value="">⏰ Quando treina?</option>
          <option value="manha"    ${periodo==='manha'   ?'selected':''}>🌅 Manhã</option>
          <option value="meio_dia" ${periodo==='meio_dia'?'selected':''}>☀️ Meio-dia</option>
          <option value="tarde"    ${periodo==='tarde'   ?'selected':''}>🌇 Tarde</option>
          <option value="noite"    ${periodo==='noite'   ?'selected':''}>🌙 Noite</option>
        </select>

        <div id="ex-${key}" style="${hide ? 'display:none' : ''}">
          ${resumoHTML}
          ${metricsHTML}

          ${!isFuturo ? `<div class="fit-area">
            <label class="fit-label" for="fit-${key}">📎 Enviar arquivo .fit</label>
            <input type="file" id="fit-${key}" accept=".fit" onchange="uploadFit('${key}', this)">
            <div id="fitinfo-${key}">${fitInfoHTML}</div>
          </div>` : ''}
          <div>
            <div class="notas-head">
              <label>Notas</label>
              <button class="info-treino" onclick="abrirTreinoInfo('${key}')" title="Ver especificação do treino"><span class="ic">ⓘ</span> saber mais</button>
            </div>
            <textarea id="desc-${key}" placeholder="Detalhes..." ${lockAttr}>${desc}</textarea>
          </div>
        </div>

        <div id="rest-${key}" style="${hide ? '' : 'display:none'}">
          <div class="rest-badge"><span class="icon">😴</span>Dia de descanso</div>
        </div>
        ${!isFuturo ? `<button class="rest-toggle" id="resttoggle-${key}" onclick="toggleRest('${key}')">
          ${hide ? '🏃 Adicionar treino' : '🛌 Marcar descanso'}
        </button>` : ''}

        ${window.NUTRICAO_ON ? `<div class="nutri-area">
          <button class="nutri-toggle" onclick="abrirNutriModal('${key}')">
            🥗 Plano alimentar do dia
          </button>
        </div>` : ''}
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
  const pd = document.getElementById(`pd-${key}`);
  if (pd) pd.style.display = hide ? 'none' : '';
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

function abrirAvaliacao(key) {
  const res = _resultados[key];
  if (!res) return;
  const ia = res.analise_ia || {};
  const tipo = document.getElementById(`tp-${key}`)?.value;
  const lbl = (TIPOS.find(tp => tp.v === tipo) || {l: ''}).l;

  const mItems = [];
  if (res.duracao_min) { const h=Math.floor(res.duracao_min/60),m=res.duracao_min%60; mItems.push(`<div class="metric"><div class="mv">${h>0?h+'h':''}${m>0?m+'min':''}</div><div class="ml">Real</div></div>`); }
  if (res.distancia_km) mItems.push(`<div class="metric"><div class="mv">${res.distancia_km} km</div><div class="ml">Distância</div></div>`);
  if (res.velocidade_media_kmh) mItems.push(`<div class="metric"><div class="mv">${res.velocidade_media_kmh} km/h</div><div class="ml">Vel. média</div></div>`);
  if (res.elevacao_m) mItems.push(`<div class="metric"><div class="mv">${res.elevacao_m} m</div><div class="ml">Altimetria</div></div>`);
  if (res.avg_hr) mItems.push(`<div class="metric"><div class="mv">${res.avg_hr} bpm</div><div class="ml">FC média</div></div>`);
  if (res.max_hr) mItems.push(`<div class="metric"><div class="mv">${res.max_hr} bpm</div><div class="ml">FC máx</div></div>`);
  if (res.cadencia_media_rpm) mItems.push(`<div class="metric"><div class="mv">${res.cadencia_media_rpm} rpm</div><div class="ml">Cad. real</div></div>`);
  if (res.cadencia_max_rpm) mItems.push(`<div class="metric"><div class="mv">${res.cadencia_max_rpm} rpm</div><div class="ml">Cad. máx</div></div>`);
  if (res.calorias) mItems.push(`<div class="metric"><div class="mv">${res.calorias}</div><div class="ml">kcal</div></div>`);
  if (res.carga_exercicio != null) mItems.push(`<div class="metric"><div class="mv">${res.carga_exercicio}</div><div class="ml">Carga de exercício</div></div>`);
  if (res.tss_esperado != null) mItems.push(`<div class="metric"><div class="mv">${res.tss_esperado}</div><div class="ml">TSS esperado</div></div>`);
  if (res.tss_obtido != null) mItems.push(`<div class="metric"><div class="mv">${res.tss_obtido}</div><div class="ml">TSS obtido</div></div>`);

  const fortes = (ia.pontos_fortes || []).map(p => `<li><span class="icon">✅</span>${p}</li>`).join('');
  const fracos = (ia.pontos_fracos || []).map(p => `<li><span class="icon">⚠️</span>${p}</li>`).join('');

  let notaHTML = '';
  if (ia.nota != null) {
    const n = Number(ia.nota);
    const cor = n >= 8 ? '#1e9e57' : (n >= 6 ? '#c08a00' : '#c62828');
    const notaTxt = Number.isInteger(n) ? n : n.toFixed(1);
    notaHTML = `<div class="nota-treino">
      <span class="nota-lbl">Nota<br>treino</span>
      <span class="nota-num" style="color:${cor}">${notaTxt}</span>
      <span class="nota-de">/ 10</span>
    </div>`;
  }

  document.getElementById('avalModalHead').innerHTML = `<h3>📊 Avaliação do treino</h3><div class="modal-sub">${lbl}</div>`;
  document.getElementById('avalModalBody').innerHTML = `
    ${mItems.length ? `<div class="metrics">${mItems.join('')}</div>` : ''}
    ${notaHTML}
    <div class="analise-bloco">
      ${ia.resumo ? `<div class="resumo-txt">"${ia.resumo}"</div>` : ''}
      ${fortes ? `<ul class="analise-lista">${fortes}</ul>` : ''}
      ${fracos ? `<ul class="analise-lista" style="margin-top:6px">${fracos}</ul>` : ''}
    </div>`;
  document.getElementById('avalModal').classList.add('show');
}

function fecharAvalModal(e) {
  document.getElementById('avalModal').classList.remove('show');
}

function abrirTreinoInfo(key) {
  const p = _planejado[key] || {};
  const tipo = document.getElementById(`tp-${key}`)?.value || p.tipo;
  if (!tipo || tipo === 'DESCANSO') return;
  const tipoInfo = TIPOS.find(tp => tp.v === tipo) || {l: tipo};
  const esp = ESPEC_TREINO[tipo];

  const cad   = document.getElementById(`cad-${key}`)?.value || p.cadencia_rpm || '';
  const notas = document.getElementById(`desc-${key}`)?.value || p.descricao || '';

  const dt = new Date(key + 'T00:00');
  const diaLabel = `${DIAS[(dt.getDay()+6)%7]} ${key.slice(8,10)}/${key.slice(5,7)}`;
  const meta = [diaLabel];
  if (p.duracao_min) meta.push(`⏱ ${p.duracao_min} min`);
  if (cad) meta.push(`🦵 ${cad} rpm`);

  let corpo = '';
  if (esp) {
    corpo += `<div class="esp-obj">${esp.obj}</div>`;
    corpo += `<div class="esp-bloco"><div class="esp-titulo">Como executar</div>`
           + `<ul class="esp-lista">${esp.estrutura.map(s => `<li>${s}</li>`).join('')}</ul></div>`;
    corpo += `<div class="esp-dica">💡 ${esp.dica}</div>`;
  }
  if (notas && notas.trim()) {
    corpo += `<div class="esp-bloco" style="margin-top:14px"><div class="esp-titulo">Notas do treino</div>`
           + `<div class="esp-notas">${notas.replace(/</g,'&lt;').replace(/\\n/g,'<br>')}</div></div>`;
  }
  if (!corpo) corpo = `<div class="esp-obj">Sem especificação detalhada para este treino.</div>`;

  document.getElementById('treinoModalHead').innerHTML = `<h3>${tipoInfo.l}</h3><div class="modal-sub">${meta.join('  ·  ')}</div>`;
  document.getElementById('treinoModalBody').innerHTML = corpo;
  document.getElementById('treinoModal').classList.add('show');
}

function fecharTreinoModal(e) {
  document.getElementById('treinoModal').classList.remove('show');
}

async function abrirNutriModal(key) {
  const tipo = document.getElementById(`tp-${key}`)?.value || 'DESCANSO';
  const periodo = document.getElementById(`pd-${key}`)?.value || '';
  const lbl  = (TIPOS.find(tp => tp.v === tipo) || {l: tipo}).l;
  const pLbl = {manha:'🌅 treino de manhã', meio_dia:'☀️ treino ao meio-dia', tarde:'🌇 treino à tarde', noite:'🌙 treino à noite'}[periodo] || '';
  const head = document.getElementById('nutriModalHead');
  const body = document.getElementById('nutriModalBody');
  head.innerHTML = `<h3>🥗 Plano alimentar do dia</h3><div class="modal-sub">${lbl}${pLbl ? ' · ' + pLbl : ''}</div>`;
  body.innerHTML = '<div style="padding:24px;text-align:center;color:#888">Carregando…</div>';
  document.getElementById('nutriModal').classList.add('show');

  try {
    const r = await fetch(`/nutrition/plano/${tipo}?data=${key}${periodo ? '&periodo=' + periodo : ''}`);
    const p = await r.json();
    const refs = (p.refeicoes || []).map(rf => {
      const itens = (rf.itens || []).map(i =>
        `<li><span>${i.texto}</span><span class="nk">${i.kcal} kcal · ${i.proteina_g}g P</span></li>`
      ).join('');
      const obs = rf.observacao ? `<div class="nutri-ref-obs">${rf.observacao}</div>` : '';
      return `<div class="nutri-ref">
        <div class="nutri-ref-h"><span class="nrn">${rf.horario} · ${rf.nome}</span>
        <span class="nrt">${rf.kcal} kcal · ${rf.proteina_g}g P</span></div>
        <ul>${itens}</ul>${obs}</div>`;
    }).join('');
    const notaTreino = p.nota_treino ? `<div class="nutri-estrat" style="background:#fff7e6;color:#8a5a00">⏰ ${p.nota_treino}</div>` : '';
    let provaHTML = '';
    if (p.prova) {
      const itens = (p.prova.itens || []).map(i => `<li>${i}</li>`).join('');
      provaHTML = `<div class="nutri-prova"><div class="np-tit">${p.prova.titulo}</div><ul>${itens}</ul></div>`;
    }
    body.innerHTML = `
      ${provaHTML}
      <div class="nutri-estrat">💡 ${p.estrategia}</div>
      <div class="nutri-meta">
        <div class="nm"><div class="nmv">${p.kcal_total}</div><div class="nml">kcal/dia</div></div>
        <div class="nm"><div class="nmv">${p.proteina_total_g}g</div><div class="nml">proteína</div></div>
      </div>
      ${notaTreino}
      ${refs}`;
  } catch(e) {
    body.innerHTML = '<div style="padding:16px;color:#c62828">Erro ao carregar plano</div>';
  }
}

function fecharNutriModal(e) {
  document.getElementById('nutriModal').classList.remove('show');
}
document.addEventListener('keydown', e => { if (e.key === 'Escape') { fecharNutriModal(); fecharAvalModal(); fecharGenModal(); } });

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
      const periodo = document.getElementById(`pd-${key}`)?.value || '';
      if (periodo) t.periodo = periodo;
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
    _atualizarBotaoProximaSemana(d.treinos || []);
  } catch {
    buildCards([]);
    _atualizarBotaoProximaSemana([]);
  }
}

function _atualizarBotaoProximaSemana(treinos) {
  const btn = document.getElementById('btnGenSemana');
  if (!btn) return;
  const hoje = new Date();
  hoje.setHours(0, 0, 0, 0);
  const ehDomingo = hoje.getDay() === 0;
  const semanaAtual = iso(getMonday(new Date())) === iso(monday);
  const todosConcluidos = treinos
    .filter(t => t.tipo !== 'DESCANSO')
    .every(t => new Date(t.data + 'T12:00:00') < hoje);
  btn.style.display = (semanaAtual && (ehDomingo || todosConcluidos)) ? '' : 'none';
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

function fecharGenModal(e) {
  document.getElementById('genModal').classList.remove('show');
}

const TIPO_CORES = {
  Z2_LONGO:'#1565c0', TIROS:'#c62828', VO2MAX:'#6a1b9a',
  TEMPO:'#e65100', FORCA:'#5d4037', RECUPERACAO:'#00695c', DESCANSO:'#607d8b',
};
const TIPO_LABELS2 = {
  Z2_LONGO:'Z2 Longo', TIROS:'Tiros', VO2MAX:'VO2Max',
  TEMPO:'Tempo', FORCA:'Força', RECUPERACAO:'Recuperação', DESCANSO:'Descanso',
};
const DIAS_PT = ['Dom','Seg','Ter','Qua','Qui','Sex','Sáb'];

let _genData = null;

async function gerarProximaSemana() {
  const btn = document.getElementById('btnGenSemana');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Gerando com IA...';

  const head = document.getElementById('genModalHead');
  const body = document.getElementById('genModalBody');
  head.innerHTML = '<h3>🤖 Próxima semana (pré-visualização)</h3><div class="modal-sub">Aguarde, analisando seus treinos...</div>';
  body.innerHTML = '<div style="padding:28px;text-align:center;color:#888">Consultando IA...</div>';
  document.getElementById('genModal').classList.add('show');

  try {
    const r = await fetch(`/workout/gerar-proxima-semana/${iso(monday)}`, {method: 'POST'});
    if (!r.ok) throw new Error(await r.text());
    const d = await r.json();
    _genData = d;

    const cards = (d.treinos || []).map(t => {
      if (t.tipo === 'DESCANSO') {
        const dia = new Date(t.data + 'T12:00:00');
        return `<div class="gen-modal-treino">
          <div class="gmt-head">
            <span class="gmt-data">${DIAS_PT[dia.getDay()]} ${t.data.slice(5)}</span>
            <span class="gmt-tipo" style="background:#607d8b">Descanso</span>
          </div>
        </div>`;
      }
      const dia = new Date(t.data + 'T12:00:00');
      const durStr = t.duracao_min ? (() => { const h=Math.floor(t.duracao_min/60),m=t.duracao_min%60; return (h>0?h+'h':'')+(m>0?m+'min':''); })() : '';
      return `<div class="gen-modal-treino">
        <div class="gmt-head">
          <span class="gmt-data">${DIAS_PT[dia.getDay()]} ${t.data.slice(5)}</span>
          <span class="gmt-tipo" style="background:${TIPO_CORES[t.tipo]||'#607d8b'}">${TIPO_LABELS2[t.tipo]||t.tipo}</span>
          ${durStr ? `<span class="gmt-dur">⏱ ${durStr}</span>` : ''}
        </div>
        ${t.descricao ? `<div class="gmt-desc">${t.descricao}</div>` : ''}
      </div>`;
    }).join('');

    head.innerHTML = `<h3>🤖 Próxima semana</h3><div class="modal-sub">${d.semana_proxima}</div>`;
    body.innerHTML = `
      ${d.analise_semana ? `<div class="gen-analise">📊 ${d.analise_semana}</div>` : ''}
      ${d.progressao ? `<div class="gen-prog">⬆️ ${d.progressao}</div>` : ''}
      ${cards}
      <button class="btn-enviar" id="btnEnviarGarmin" onclick="enviarParaGarmin()">
        📡 Salvar + Enviar pro Garmin
      </button>`;
  } catch(e) {
    body.innerHTML = `<div style="padding:16px;color:#c62828">Erro: ${e.message}</div>`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = '🤖 Gerar próxima semana';
  }
}

async function enviarParaGarmin() {
  if (!_genData) return;
  const btn = document.getElementById('btnEnviarGarmin');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Enviando pro Garmin...';

  const treinos = (_genData.treinos || []).map(t => ({
    data: t.data,
    tipo: t.tipo,
    duracao_min:  t.duracao_min  || null,
    descricao:    t.descricao    || null,
    cadencia_rpm: t.cadencia_rpm || null,
  }));

  try {
    const r = await fetch('/workout/enviar-garmin', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        semana_inicio: _genData.semana_proxima,
        objetivo: _genData.progressao || '',
        treinos,
      }),
    });
    if (!r.ok) throw new Error(await r.text());
    const d = await r.json();
    fecharGenModal();
    toast(`✅ ${d.enviados} treino(s) enviado(s) ao Garmin!`, 'ok');
    // se o usuário estiver visualizando a próxima semana, recarrega
    const proxData = new Date(_genData.semana_proxima + 'T12:00:00');
    if (iso(monday) === _genData.semana_proxima) await load();
  } catch(e) {
    btn.disabled = false;
    btn.innerHTML = '📡 Salvar + Enviar pro Garmin';
    toast('❌ Erro ao enviar: ' + e.message, 'err');
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

async function carregarProva() {
  const panel = document.getElementById('provaPanel');
  if (!panel) return;
  let d;
  try {
    const r = await fetch('/workout/provas/proxima');
    if (!r.ok) return;
    d = await r.json();
  } catch(e) { return; }

  if (!d || !d.prova) {
    panel.innerHTML = `<div class="prova-cta">🎯 <a href="/workout/calendario">Cadastre sua próxima prova</a> para a IA periodizar seus treinos.</div>`;
    return;
  }

  const esc = s => (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const dias = d.dias_restantes;
  const count = dias <= 0 ? '🏁 É hoje!' : (dias === 1 ? 'Falta 1 dia' : 'Faltam ' + dias + ' dias');
  const p = d.prova;
  const [y,m,dd] = (p.data||'').split('-');
  const dataFmt = dd ? (dd+'/'+m+'/'+y) : (p.data||'');
  const sub = [];
  if (p.local) sub.push('📍 ' + esc(p.local));
  if (p.distancia_km) sub.push(p.distancia_km + ' km');
  if (p.altimetria_m) sub.push(p.altimetria_m + ' m');
  if (p.terreno) sub.push(esc(p.terreno));

  const focos = (d.focos || []).map(f => `<li><span>🎯</span><span>${esc(f)}</span></li>`).join('');
  const focosHTML = focos ? `<div class="pp-focos"><div class="pf-titulo">Focos até a prova</div><ul>${focos}</ul></div>` : '';

  panel.innerHTML = `<div class="prova-panel">
    <div class="pp-top">
      <div>
        <div class="pp-label">Próxima prova</div>
        <div class="pp-nome">${esc(p.nome)}</div>
      </div>
      <span class="pp-fase">${esc(d.fase_label || '')}</span>
    </div>
    <div class="pp-count">${count}</div>
    <div class="pp-sub">${dataFmt}${sub.length ? '  ·  ' + sub.join('  ·  ') : ''}</div>
    ${focosHTML}
    <div style="margin-top:10px"><a class="pp-link" href="/workout/calendario">Gerenciar provas →</a></div>
  </div>`;
}

load();
carregarProva();
</script>
</body>
</html>"""


@router.get("/", response_class=HTMLResponse)
async def portal(request: Request):
    from app.services.user_service import get_por_id
    try:
        u = await get_por_id(request.state.user_id)
    except Exception:
        u = None
    if u is None:
        u = {}
    nome = u.get("nome", "")
    perder_peso = bool((u.get("preferencias") or {}).get("perder_peso"))
    # Nutrição também aparece para quem tem prova futura (fueling/performance),
    # mesmo sem objetivo de emagrecer.
    if not perder_peso:
        try:
            from app.services.prova_service import proxima_prova
            perder_peso = await proxima_prova(request.state.user_id) is not None
        except Exception:
            pass

    nav_nutri = (
        '<a href="/nutrition/config">⏰ Horários</a>\n'
        '    <a href="/nutrition/alimentos">🍽️ Alimentos</a>\n'
        '    <a href="/nutrition/guia">🥗 Nutrição</a>\n'
        '    <a href="/nutrition/ajuste">🍔 Fuga do plano</a>\n'
        '    <a href="/nutrition/chat">💬 Ajustar cardápio</a>'
    ) if perder_peso else ""

    nav_user = f'<span class="nav-user">👤 {nome}</span>' if nome else ""

    nutricao_on_js = "true" if perder_peso else "false"

    return (
        HTML
        .replace("{{NAV_NUTRI}}", nav_nutri)
        .replace("{{NAV_USER}}", nav_user)
        .replace("{{NUTRICAO_ON}}", nutricao_on_js)
    )
