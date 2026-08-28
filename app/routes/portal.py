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
      --green: #0f8b7d; --green-dark: #0b6d62; --green2: #25d366;
      --accent: #14b8a6; --bg: #eef1f6;
      --card: #fff; --text: #0f172a; --muted: #64748b; --border: #e6e9ef;
      --radius: 16px; --radius-sm: 11px;
      --shadow-sm: 0 1px 2px rgba(15,23,42,.04), 0 1px 3px rgba(15,23,42,.06);
      --shadow-md: 0 4px 10px -2px rgba(15,23,42,.08), 0 2px 6px -2px rgba(15,23,42,.05);
      --shadow-lg: 0 16px 32px -8px rgba(15,23,42,.14), 0 6px 12px -6px rgba(15,23,42,.08);
      --grad-green: linear-gradient(135deg, #0f8b7d 0%, #14b8a6 100%);
      --grad-nav: linear-gradient(120deg, #0e8577 0%, #128c7e 55%, #14a291 100%);
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Inter', sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }
    ::selection { background: rgba(20,184,166,.28); }

    nav { background: var(--grad-nav); color: #fff; padding: 14px 24px; display: flex; align-items: center; gap: 12px; box-shadow: 0 4px 20px -4px rgba(14,138,125,.45); position: sticky; top: 0; z-index: 50; }
    nav .logo { font-size: 1.35rem; font-weight: 700; }
    nav .sub  { font-size: 0.8rem; opacity: .8; }
    nav > div:first-of-type { flex-shrink: 0; }
    /* flex-wrap + justify-end: com muitos itens (nutrição habilitada + admin +
       assinatura) a barra passava a empurrar o layout em vez de quebrar. */
    nav .nav-links { margin-left: auto; display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px 14px; align-items: center; }
    nav .nav-links a { color: #fff; text-decoration: none; font-size: 0.88rem; opacity: .85; white-space: nowrap; }
    /* Status de conexão é ícone: ocupa o espaço de um emoji e o rótulo vive no
       tooltip. Um texto de 17 caracteres no header não paga o que informa. */
    nav .nav-links a.nav-icone { font-size: 1.05rem; opacity: .95; }
    nav .nav-links a:hover { opacity: 1; text-decoration: underline; }
    nav .nav-toggle { display: none; margin-left: auto; background: rgba(255,255,255,.15); border: none; color: #fff; font-size: 1.4rem; line-height: 1; width: 42px; height: 42px; border-radius: 8px; cursor: pointer; }
    nav .nav-user { color: rgba(255,255,255,.75); font-size: 0.85rem; font-weight: 600; white-space: nowrap; }
    .admin-nav-link { color:#fff; text-decoration:none; font-size:.8rem; font-weight:700; background:rgba(255,255,255,.22); padding:4px 13px; border-radius:20px; white-space:nowrap; }

    main { max-width: 1400px; margin: 0 auto; padding: 24px 20px 80px; }

    .week-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 24px; flex-wrap: wrap; }
    .week-bar .arrow { background: var(--card); border: 1px solid var(--border); border-radius: 50%; width: 40px; height: 40px; cursor: pointer; font-size: 1.1rem; color: var(--text); display: flex; align-items: center; justify-content: center; transition: transform .18s, box-shadow .18s, border-color .18s, color .18s; box-shadow: var(--shadow-sm); }
    .week-bar .arrow:hover { border-color: var(--green); color: var(--green); transform: translateY(-1px); box-shadow: var(--shadow-md); }
    .week-label { font-size: 1.1rem; font-weight: 800; flex: 1; text-align: center; letter-spacing: -.01em; }
    .today-btn { background: none; border: none; color: var(--green); font-size: 0.85rem; text-decoration: underline; cursor: pointer; }

    .card { background: var(--card); border-radius: var(--radius); padding: 22px; margin-bottom: 20px; box-shadow: var(--shadow-sm); border: 1px solid var(--border); }

    .prova-panel { background: linear-gradient(135deg, #0e8a7d 0%, #14b8a6 100%); color: #fff; border-radius: var(--radius); padding: 20px 22px; margin-bottom: 20px; box-shadow: 0 10px 28px -8px rgba(14,138,125,.5); }
    .prova-panel .pp-top { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    .prova-panel .pp-label { font-size: .7rem; font-weight: 700; text-transform: uppercase; letter-spacing: .8px; opacity: .85; }
    .prova-panel .pp-nome { font-size: 1.15rem; font-weight: 800; }
    .prova-panel .pp-fase { margin-left: auto; background: rgba(255,255,255,.2); border-radius: 20px; padding: 4px 12px; font-size: .75rem; font-weight: 700; white-space: nowrap; }
    .prova-panel .pp-sub { font-size: .85rem; opacity: .92; margin-top: 3px; }
    .adap-panel { background: var(--card); border: 1px solid var(--green); border-left-width: 4px; border-radius: 12px; padding: 16px 18px; margin-bottom: 20px; box-shadow: var(--shadow-sm); }
    .adap-panel h4 { margin: 0 0 6px; font-size: .98rem; }
    .adap-panel .ad-resumo { font-size: .88rem; color: var(--muted); margin-bottom: 10px; }
    .adap-panel ul { margin: 0 0 12px; padding-left: 18px; font-size: .88rem; line-height: 1.6; }
    .adap-panel .ad-motivo { color: var(--muted); }
    .adap-panel button { border: none; border-radius: 8px; padding: 8px 14px; font-weight: 700; cursor: pointer; margin-right: 8px; }
    .ajuste-ia { background: rgba(46,125,50,.08); border: 1px solid var(--border); border-left: 3px solid var(--green); border-radius: 8px; padding: 7px 10px; margin-bottom: 10px; font-size: .78rem; line-height: 1.45; }
    .ajuste-ia .ai-motivo { color: var(--muted); margin-top: 2px; }
    .adap-panel .ad-ok { background: var(--green); color: #fff; }
    .adap-panel .ad-no { background: transparent; color: var(--muted); border: 1px solid var(--border); }
    .prova-panel .pp-count { font-size: 1.4rem; font-weight: 800; margin: 8px 0 2px; }
    .prova-panel .pp-focos { background: rgba(255,255,255,.13); border-radius: 10px; padding: 10px 12px; margin-top: 12px; }
    .prova-panel .pp-focos .pf-titulo { font-size: .72rem; font-weight: 700; text-transform: uppercase; letter-spacing: .6px; opacity: .9; margin-bottom: 6px; }
    .prova-panel .pp-focos ul { list-style: none; }
    .prova-panel .pp-focos li { font-size: .85rem; padding: 3px 0; display: flex; gap: 7px; align-items: flex-start; line-height: 1.35; }
    .prova-panel a.pp-link { color: #fff; text-decoration: underline; font-size: .82rem; opacity: .9; }
    /* Provas seguintes: uma linha cada, mais discretas que a próxima — quem
       exige ação agora é a primeira. */
    .prova-panel .pp-seguintes { margin-top: 12px; border-top: 1px solid rgba(255,255,255,.22); padding-top: 10px; }
    .prova-panel .ps-linha { display: flex; align-items: baseline; gap: 10px; padding: 5px 0; font-size: .85rem; }
    .prova-panel .ps-linha + .ps-linha { border-top: 1px solid rgba(255,255,255,.1); }
    .prova-panel .ps-data { font-weight: 800; font-variant-numeric: tabular-nums; opacity: .95; flex-shrink: 0; }
    .prova-panel .ps-nome { font-weight: 600; flex: 1; min-width: 0; }
    .prova-panel .ps-nome small { opacity: .75; font-weight: 400; font-size: .8rem; }
    .prova-panel .ps-dias { opacity: .85; white-space: nowrap; flex-shrink: 0; }
    .prova-panel .ps-fase { background: rgba(255,255,255,.16); border-radius: 20px; padding: 2px 9px; font-size: .68rem; font-weight: 700; white-space: nowrap; flex-shrink: 0; }
    @media (max-width: 640px) {
      .prova-panel .ps-linha { flex-wrap: wrap; gap: 4px 8px; }
      .prova-panel .ps-nome { flex-basis: 100%; order: 3; }
    }
    .prova-cta { background: #fff; border: 1.5px dashed var(--green); border-radius: 12px; padding: 14px 18px; margin-bottom: 20px; text-align: center; }
    .prova-cta a { color: var(--green); font-weight: 700; text-decoration: none; font-size: .92rem; }
    .section-label { font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: .8px; color: var(--muted); margin-bottom: 8px; }
    .card textarea { width: 100%; border: 1.5px solid var(--border); border-radius: 8px; padding: 10px 12px; font-size: .95rem; font-family: inherit; resize: vertical; min-height: 72px; outline: none; transition: border-color .2s; line-height: 1.5; }
    .card textarea:focus { border-color: var(--green); }

    .novato-panel { background: #fff; border: 1.5px dashed var(--green); border-radius: 14px; padding: 28px 22px; margin-bottom: 24px; text-align: center; }
    .novato-panel .np-emoji { font-size: 2.4rem; margin-bottom: 8px; }
    .novato-panel .np-titulo { font-size: 1.15rem; font-weight: 800; margin-bottom: 6px; }
    .novato-panel .np-sub { font-size: .92rem; color: var(--muted); line-height: 1.55; max-width: 560px; margin: 0 auto 18px; }
    .novato-panel .np-botoes { display: flex; gap: 12px; justify-content: center; flex-wrap: wrap; }
    .novato-panel .np-botoes .btn { text-decoration: none; }
    @keyframes bike-wheel { to { transform: rotate(360deg); } }
    @keyframes bike-move { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-4px); } }
    .bike-loading { display: flex; flex-direction: column; align-items: center; gap: 14px; padding: 10px 0; }
    .bike-loading svg { animation: bike-move 0.7s ease-in-out infinite; }
    .bike-loading .wheel-f { transform-origin: 74px 54px; animation: bike-wheel 0.5s linear infinite; }
    .bike-loading .wheel-r { transform-origin: 26px 54px; animation: bike-wheel 0.5s linear infinite; }
    .bike-loading .np-titulo { margin-bottom: 2px; }
    .bike-loading .np-sub { margin-bottom: 0; }
    .bike-progress-wrap { width: 260px; background: #e0e0e0; border-radius: 99px; height: 8px; overflow: hidden; }
    .bike-progress-bar { height: 100%; background: #2e7d32; border-radius: 99px; width: 0%; transition: width 0.4s ease; }
    .bike-progress-pct { font-size: .75rem; color: #555; margin-top: 2px; }
    .days-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 10px; margin-bottom: 24px; align-items: start; }
    @media(max-width:1000px){ .days-grid { grid-template-columns: repeat(4,1fr); } }
    @media(max-width:760px) { .days-grid { grid-template-columns: repeat(2,1fr); } }
    @media(max-width:560px) { .days-grid { grid-template-columns: 1fr; } }

    .day-col { display: flex; flex-direction: column; gap: 10px; }

    .extra-card { background: var(--card); border-radius: var(--radius-sm); overflow: hidden; box-shadow: var(--shadow-sm); border: 1px dashed var(--border); }
    .extra-head { padding: 8px 10px; display: flex; align-items: center; justify-content: space-between; gap: 6px; }
    .extra-chip { color: #fff; padding: 3px 9px; border-radius: 999px; font-size: .7rem; font-weight: 700; white-space: nowrap; }
    .extra-remove { background: none; border: none; color: var(--muted); cursor: pointer; font-size: .85rem; padding: 2px 4px; }
    .extra-remove:hover { color: #c62828; }
    .extra-body { padding: 0 10px 10px; display: flex; flex-direction: column; gap: 6px; }
    .extra-meta { font-size: .72rem; color: var(--muted); display: flex; gap: 10px; flex-wrap: wrap; }
    .extra-desc { font-size: .8rem; color: var(--text); white-space: pre-wrap; line-height: 1.4; }
    .extra-check { font-size: .75rem; color: var(--muted); display: flex; align-items: center; gap: 5px; cursor: pointer; }
    .extra-edit-toggle { background: none; border: none; color: var(--muted); font-size: .72rem; cursor: pointer; text-decoration: underline; padding: 2px 0; text-align: left; }
    .extra-edit-toggle:hover { color: var(--text); }
    .extra-form { background: var(--card); border-radius: var(--radius-sm); border: 1px solid var(--border); padding: 10px; display: flex; flex-direction: column; gap: 8px; box-shadow: var(--shadow-sm); }
    .extra-form select, .extra-form input[type=number], .extra-form textarea {
      width: 100%; border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px;
      font-size: .82rem; font-family: inherit; outline: none; background: #fff; color: inherit;
    }
    .extra-form textarea { min-height: 44px; resize: vertical; }
    .extra-form-actions { display: flex; gap: 6px; }
    .extra-form-actions button { flex: 1; padding: 7px; border-radius: 6px; border: none; font-size: .76rem; font-weight: 700; cursor: pointer; }
    .extra-form-actions .ef-save { background: var(--green); color: #fff; }
    .extra-form-actions .ef-cancel { background: none; border: 1px solid var(--border); color: var(--muted); }

    .day-card { background: var(--card); border-radius: var(--radius-sm); overflow: hidden; box-shadow: var(--shadow-sm); border: 1px solid var(--border); transition: transform .18s, box-shadow .18s; }
    .day-card:hover { box-shadow: var(--shadow-lg); transform: translateY(-3px); }
    .day-card.today { outline: 2.5px solid var(--green); outline-offset: 1px; }
    .day-card.realizado { background: #d9f7e1; }
    .day-card.realizado .day-body { background: #d9f7e1; }
    .day-card.perdido { background: #ffe2bf; }
    .day-card.perdido .day-body { background: #ffe2bf; }
    .day-card.futuro { opacity: .72; }
    .day-card.futuro .day-body select,
    .day-card.futuro .day-body textarea,
    .day-card.futuro .day-body input[type=file] { pointer-events: none; opacity: .6; }
    .day-card.futuro .rest-toggle { pointer-events: none; opacity: .4; }
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
    .indoor-area { margin-top: 8px; border-top: 1px dashed var(--border); padding-top: 8px; }
    .indoor-toggle { display: flex; gap: 4px; border-radius: 8px; overflow: hidden; border: 1.5px solid var(--border); }
    .indoor-toggle button { flex: 1; padding: 7px 4px; border: none; font-size: .78rem; font-weight: 700; cursor: pointer; background: #f3f4f6; color: var(--muted); transition: .15s; }
    .indoor-toggle button.ativo { background: var(--green); color: #fff; }
    .indoor-toggle button:disabled { opacity: .5; cursor: not-allowed; }
    .indoor-sync-msg { font-size: .72rem; margin-top: 4px; text-align: center; min-height: 14px; color: var(--muted); }
    .erg-dl { display: inline-flex; align-items: center; gap: 6px; margin-top: 8px; font-size: .76rem; font-weight: 700; color: var(--green); text-decoration: none; border: 1.5px solid #cfe9e3; background: #f1f8f6; border-radius: 8px; padding: 6px 10px; }
    .erg-dl:hover { background: #e6f3ef; }
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

    .treino-chart { margin-bottom: 16px; }
    .tc-bars { display: flex; align-items: flex-end; height: 96px; gap: 2px; }
    .tc-bar { border-radius: 4px 4px 0 0; min-width: 3px; position: relative; cursor: pointer; filter: brightness(1); transition: filter .15s; }
    .tc-bar:hover, .tc-bar:focus-visible { filter: brightness(1.12); outline: none; }
    .tc-tip { position: absolute; bottom: calc(100% + 6px); left: 50%; transform: translate(-50%, 2px); background: #0b0b0b; color: #fff; font-size: .7rem; line-height: 1.4; white-space: nowrap; padding: 6px 9px; border-radius: 7px; opacity: 0; visibility: hidden; pointer-events: none; transition: opacity .12s, transform .12s; z-index: 5; box-shadow: 0 4px 12px rgba(0,0,0,.25); }
    .tc-tip b { font-weight: 700; }
    .tc-bar:hover .tc-tip, .tc-bar:focus-visible .tc-tip { opacity: 1; visibility: visible; transform: translate(-50%, 0); }
    .tc-axis { display: flex; justify-content: space-between; font-size: .68rem; color: var(--muted); font-weight: 600; margin-top: 5px; }
    .tc-legend { display: flex; align-items: center; gap: 5px; margin-top: 9px; font-size: .68rem; color: var(--muted); }
    .tc-legend .tc-sw { width: 20px; height: 8px; border-radius: 2px; display: inline-block; }
    .tc-loading, .tc-empty { font-size: .78rem; color: var(--muted); padding: 10px 0; text-align: center; }

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
    .tipo-ACADEMIA    { background: #2e7d32; }
    .tipo-RECUPERACAO { background: #00695c; }
    .tipo-DESCANSO    { background: #607d8b; }
    .tipo-TESTE_FTP   { background: #7c3aed; }
    .academia-bloco { background: #e8f5e9; border-radius: var(--radius-sm); padding: 8px 12px; border: 1px solid #2e7d32; box-shadow: var(--shadow-sm); }
    .academia-bloco.clickable { cursor: pointer; transition: transform .15s, box-shadow .15s; }
    .academia-bloco.clickable:hover { transform: translateY(-2px); box-shadow: var(--shadow-lg); }
    .academia-bloco .ac-header { display: flex; align-items: center; justify-content: space-between; gap: 6px; }
    .academia-bloco .ac-titulo { font-size: .78rem; font-weight: 700; color: #2e7d32; }
    .academia-bloco .ac-dur { font-size: .7rem; color: #555; margin-left: auto; }
    .academia-bloco .ac-arrow { font-size: .62rem; color: #2e7d32; transition: transform .15s; }
    .academia-bloco.expanded .ac-arrow { transform: rotate(90deg); }
    .academia-bloco .ac-foco { font-size: .7rem; color: #388e3c; font-style: italic; margin-top: 4px; }
    .academia-bloco .ac-detalhes { display: none; margin-top: 8px; }
    .academia-bloco.expanded .ac-detalhes { display: block; }
    .academia-bloco .ac-porque { font-size: .75rem; color: #444; line-height: 1.4; margin-bottom: 6px; background: #fff; border-radius: 4px; padding: 5px 8px; }
    .academia-bloco .ac-exercicios { list-style: none; padding: 0; margin: 0; }
    .academia-bloco .ac-exercicios li { font-size: .75rem; color: var(--text); line-height: 1.5; padding: 2px 0; border-bottom: 1px solid #c8e6c9; }
    .academia-bloco .ac-exercicios li:last-child { border-bottom: none; }
    .academia-bloco .ac-obs { font-size: .72rem; color: #666; line-height: 1.4; margin-top: 4px; }
    .academia-bloco .ac-check { cursor: default; }

    /* Checklist de academia: o atleta marca cada exercício conforme executa e
       fecha a sessão dando a nota de sensação. Não há Garmin para musculação —
       este é o único "sensor" da sessão.
       ATENÇÃO à especificidade: `.day-body label` impõe uppercase + display:block
       e `.day-body input[type=number]` impõe width:100%. Sem sobrepor as duas,
       o item desmonta (nome em caixa alta, quebrado) e o campo de carga vaza
       para fora do card. Por isso os seletores abaixo são qualificados. */
    .ex-progresso { font-size: .72rem; color: var(--muted); font-weight: 700; margin-bottom: 6px; }
    .ex-check-list { display: flex; flex-direction: column; gap: 4px; }
    .ex-check-item { display: flex; flex-direction: column; gap: 5px; padding: 7px 8px;
      border: 1px solid var(--border); border-radius: 6px; background: var(--card);
      transition: background .12s, border-color .12s; }
    .ex-check-item:hover { border-color: #2e7d32; }
    .ex-check-item.feito { background: #e8f5e9; border-color: #a5d6a7; }

    .ex-check-item label.ex-check-main { display: flex; align-items: flex-start; gap: 7px;
      cursor: pointer; margin: 0; font-size: .76rem; font-weight: 500; line-height: 1.35;
      color: var(--text); text-transform: none; letter-spacing: normal; }
    .ex-check-item label.ex-check-main input[type=checkbox] { flex: 0 0 auto; width: 15px;
      height: 15px; margin-top: 1px; accent-color: #2e7d32; cursor: pointer; }
    .ex-nome { min-width: 0; overflow-wrap: anywhere; }
    .ex-principal { display: block; }
    .ex-check-item.feito .ex-principal { text-decoration: line-through; opacity: .5; }
    /* O "porquê" do exercício some depois de feito: já cumpriu o papel e a
       coluna do calendário é estreita — 5 exercícios com justificativa viram
       um card altíssimo. */
    .ex-detalhe { display: block; margin-top: 2px; font-size: .67rem; font-weight: 400;
      line-height: 1.3; color: var(--muted); }
    .ex-check-item.feito .ex-detalhe { display: none; }

    .ex-carga { display: flex; align-items: center; gap: 5px; margin-left: 22px;
      font-size: .67rem; color: var(--muted); }
    .ex-check-item .ex-carga input[type=number] { flex: 0 0 58px; width: 58px; padding: 3px 6px;
      border: 1px solid var(--border); border-radius: 5px; background: var(--card);
      color: var(--text); font-size: .76rem; text-align: right; -moz-appearance: textfield; }
    .ex-carga input::-webkit-outer-spin-button,
    .ex-carga input::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
    .ex-check-item .ex-carga input[type=number]:focus { outline: none; border-color: #2e7d32; }

    .sensacao-box { border-top: 1px dashed var(--border); margin-top: 11px; padding-top: 9px; }
    .sensacao-btns { display: flex; gap: 4px; }
    .sensacao-btns button { flex: 1 1 0; min-width: 0; padding: 6px 0; border: 1px solid var(--border);
      border-radius: 6px; background: var(--card); font-size: 1.05rem; line-height: 1.1;
      cursor: pointer; transition: background .12s, border-color .12s; }
    .sensacao-btns button:hover { border-color: #2e7d32; }
    .sensacao-btns button.ativo { background: #2e7d32; border-color: #2e7d32; }
    .sensacao-sel { font-size: .7rem; color: var(--muted); text-align: center;
      margin-top: 5px; min-height: 14px; }
    .ex-msg { font-size: .7rem; margin-top: 6px; min-height: 14px; overflow-wrap: anywhere; }
    .ex-edit-toggle { background: none; border: none; color: var(--muted); font-size: .72rem;
      cursor: pointer; text-decoration: underline; padding: 5px 0 0; }
    .ex-edit-toggle:hover { color: var(--text); }

    .actions { display: flex; gap: 12px; flex-wrap: wrap; }
    .btn { padding: 13px 22px; border: none; border-radius: 12px; font-size: .95rem; font-weight: 700; cursor: pointer; transition: transform .15s, box-shadow .15s, background .2s, border-color .2s, color .2s; display: flex; align-items: center; gap: 6px; }
    .btn-save  { background: var(--grad-green);  color: #fff; flex: 1; justify-content: center; box-shadow: 0 4px 12px -2px rgba(15,139,125,.4); }
    .btn-save:hover:not(:disabled)  { transform: translateY(-2px); box-shadow: 0 9px 20px -4px rgba(15,139,125,.5); }
    .btn-test  { background: linear-gradient(135deg, #25d366 0%, #16b34a 100%); color: #fff; box-shadow: 0 4px 12px -2px rgba(37,211,102,.4); }
    .btn-test:hover:not(:disabled)  { transform: translateY(-2px); box-shadow: 0 9px 20px -4px rgba(37,211,102,.5); }
    .btn-sec   { background: var(--card); color: var(--text); border: 1.5px solid var(--border); box-shadow: var(--shadow-sm); }
    .btn-sec:hover:not(:disabled)   { border-color: var(--green); color: var(--green); transform: translateY(-2px); box-shadow: var(--shadow-md); }
    .btn-ftp   { background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%); color: #fff; box-shadow: 0 4px 12px -2px rgba(124,58,237,.4); }
    .btn-ftp:hover:not(:disabled)   { transform: translateY(-2px); box-shadow: 0 9px 20px -4px rgba(124,58,237,.5); }
    .btn:active:not(:disabled) { transform: translateY(0); }
    .btn:disabled { opacity: .5; cursor: not-allowed; }

    .spinner { width: 16px; height: 16px; border: 2px solid rgba(255,255,255,.4); border-top-color: #fff; border-radius: 50%; animation: spin .7s linear infinite; }
    @keyframes spin { to { transform: rotate(360deg); } }

    .toast { position: fixed; bottom: 28px; left: 50%; transform: translateX(-50%); padding: 12px 28px; border-radius: 10px; font-size: .9rem; font-weight: 600; z-index: 9999; opacity: 0; pointer-events: none; transition: opacity .3s; white-space: nowrap; }
    .toast.show { opacity: 1; }
    .toast.ok  { background: #2e7d32; color: #fff; }
    .toast.err { background: #c62828; color: #fff; }
    .toast.info{ background: #323232; color: #fff; }

    .theme-btn { background: rgba(255,255,255,.15); border: none; color: #fff; border-radius: 8px; padding: 5px 9px; cursor: pointer; font-size: 1rem; line-height: 1.4; flex-shrink: 0; }
    .theme-btn:hover { background: rgba(255,255,255,.28); }

    /* ── Dark theme ── */
    [data-theme="dark"] { --bg:#0b1220; --card:#1a2536; --text:#e5e7eb; --muted:#94a3b8; --border:#2a3852; --green:#1db39e; --accent:#2dd4bf;
      --shadow-sm: 0 1px 3px rgba(0,0,0,.45);
      --shadow-md: 0 4px 12px -2px rgba(0,0,0,.55);
      --shadow-lg: 0 18px 36px -10px rgba(0,0,0,.65);
      --grad-green: linear-gradient(135deg, #14a897 0%, #1db39e 100%); }
    [data-theme="dark"] body { background: var(--bg); color: var(--text); }
    [data-theme="dark"] .card,
    [data-theme="dark"] .day-card { background: var(--card); }
    [data-theme="dark"] .week-bar .arrow { background: var(--card); color: var(--text); border-color: var(--border); }
    [data-theme="dark"] .btn-sec { background: var(--card); color: var(--text); border-color: var(--border); }
    [data-theme="dark"] .btn-sec:hover:not(:disabled) { border-color: var(--green); color: var(--green); background: var(--card); }
    [data-theme="dark"] .modal { background: #1f2937; }
    [data-theme="dark"] .modal-close { background: #374151; color: var(--text); }
    [data-theme="dark"] .modal-close:hover { background: #4b5563; }
    [data-theme="dark"] .day-body select,
    [data-theme="dark"] .day-body input[type=number],
    [data-theme="dark"] .day-body textarea { background: #111827; color: var(--text); border-color: var(--border); }
    [data-theme="dark"] .card textarea { background: #111827; color: var(--text); border-color: var(--border); }
    [data-theme="dark"] .metric { background: #111827; }
    [data-theme="dark"] .treino-resumo,
    [data-theme="dark"] .analise-bloco,
    [data-theme="dark"] .nota-treino,
    [data-theme="dark"] .gen-modal-treino,
    [data-theme="dark"] .esp-lista li,
    [data-theme="dark"] .esp-notas,
    [data-theme="dark"] .nutri-estrat { background: #111827; }
    [data-theme="dark"] .treino-resumo li { border-bottom-color: var(--border); }
    [data-theme="dark"] .gen-analise { background: #2a1900; color: #fbbf24; }
    [data-theme="dark"] .gen-prog { background: #0d2020; color: #6ee7b7; }
    [data-theme="dark"] .indoor-toggle button { background: #1f2937; color: var(--muted); }
    [data-theme="dark"] .novato-panel { background: var(--card); }
    [data-theme="dark"] .prova-cta { background: var(--card); border-color: var(--green); }
    [data-theme="dark"] .nutri-prova { background: #0d2020; border-color: #1a5e40; }
    [data-theme="dark"] .nutri-prova .np-tit { color: #6ee7b7; }
    [data-theme="dark"] .nutri-prova li { color: var(--text); }
    [data-theme="dark"] .bike-progress-wrap { background: #374151; }
    [data-theme="dark"] .day-card.realizado { background: #1a3a1f; }
    [data-theme="dark"] .day-card.realizado .day-body { background: #1a3a1f; }
    [data-theme="dark"] .day-card.perdido { background: #3a2200; }
    [data-theme="dark"] .day-card.perdido .day-body { background: #3a2200; }
    [data-theme="dark"] .aval-btn { background: #1a2a40; border-color: #2a4060; color: #93c5fd; }
    [data-theme="dark"] .nutri-toggle { background: #0d2020; border-color: #1a5e40; color: #6ee7b7; }
    [data-theme="dark"] .nutri-toggle:hover { background: #112820; }
    [data-theme="dark"] .nutri-ref { border-bottom-color: var(--border); }
    [data-theme="dark"] .academia-bloco { background: #0d2020; border-color: #1a5e40; }
    [data-theme="dark"] .academia-bloco .ac-titulo { color: #6ee7b7; }
    [data-theme="dark"] .academia-bloco .ac-arrow { color: #6ee7b7; }
    [data-theme="dark"] .academia-bloco .ac-porque { background: #1f2937; color: var(--text); }
    [data-theme="dark"] .academia-bloco .ac-exercicios li { border-bottom-color: #1a5e40; }
    [data-theme="dark"] .ex-check-item { background: #111827; }
    [data-theme="dark"] .ex-check-item.feito { background: #0d2020; border-color: #1a5e40; }
    [data-theme="dark"] .sensacao-btns button { background: #111827; }
    [data-theme="dark"] .ex-carga input { background: #1f2937; }
    [data-theme="dark"] .extra-form select,
    [data-theme="dark"] .extra-form input[type=number],
    [data-theme="dark"] .extra-form textarea { background: #111827; color: var(--text); border-color: var(--border); }

    /* Ajustes para celular */
    @media(max-width:640px) {
      nav { position: relative; padding: 12px 16px; }
      nav .nav-toggle { display: block; }
      nav .nav-links {
        display: none;
        position: absolute; top: 100%; left: 0; right: 0;
        flex-direction: column; gap: 0;
        background: var(--green);
        box-shadow: 0 8px 24px rgba(0,0,0,.28);
        z-index: 999;
        margin-left: 0;
      }
      nav.open .nav-links { display: flex; }
      nav .nav-links a, nav .nav-links .admin-nav-link {
        font-size: 1rem; opacity: 1; padding: 14px 20px;
        border-top: 1px solid rgba(255,255,255,.15);
      }
      nav .nav-links .admin-nav-link {
        background: none; border-radius: 0; color: #fff; font-size: 1rem;
        font-weight: 600; white-space: normal;
      }
      nav .nav-links .nav-user {
        font-size: 1rem; padding: 14px 20px; opacity: .75;
        border-top: 1px solid rgba(255,255,255,.15); display: block;
      }
      main { padding: 16px 12px 80px; }
      .card { padding: 16px; }
      .week-label { font-size: .95rem; }
      .toast { white-space: normal; max-width: 90vw; text-align: center; }
    }
  </style>
  <script>(function(){var t=localStorage.getItem('mtb-tema')||'__TEMA__';document.documentElement.setAttribute('data-theme',t)})();</script>
</head>
<body>

<nav>
  <span style="font-size:1.7rem">🚵</span>
  <div>
    <div class="logo">MTB Nutrition</div>
    <div class="sub">Portal de Treinos</div>
  </div>
  <button class="theme-btn" id="themeBtn" onclick="toggleTema()" title="Alternar tema claro/escuro">🌙</button>
  <button class="nav-toggle" aria-label="Abrir menu" onclick="this.closest('nav').classList.toggle('open')">☰</button>
  <div class="nav-links">
    {{NAV_NUTRI}}
    <a href="/workout/evolucao">📈 Evolução</a>
    <a href="/workout/calendario">📅 Provas</a>
    <a href="/workout/perfil">👤 Perfil</a>
    {{GARMIN_NAV}}
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

  <div id="adapPanel"></div>

  <div id="provaPanel"></div>

  <div class="card">
    <div class="section-label">💡 Objetivo / Foco da Semana</div>
    <textarea id="objetivo" placeholder="Ex: Semana de base aeróbica com 2 sessões de Z2 longo. Foco em manter FC abaixo de 153 bpm. Volume total: ~12h de pedal..."></textarea>
  </div>

  <div class="section-label" style="margin-bottom:12px">📅 Treinos da Semana</div>
  <div class="novato-panel" id="novatoPanel" style="display:none">
    <div class="np-emoji">🚴</div>
    <div class="np-titulo" id="npTitulo">Sua semana está vazia</div>
    <div class="np-sub" id="npSub">Você ainda não tem treinos nesta semana. Posso montar um plano pra você
      a partir do seu perfil (idade, peso, objetivo e dias de treino) — ou você conecta
      o Garmin para importar seus treinos.</div>
    <div class="np-botoes">
      <button class="btn btn-save" id="btnGerarNovato" onclick="gerarPrimeiraSemana()">✨ Montar minha semana</button>
      {{GARMIN_BTN}}
    </div>
  </div>

  <div class="days-grid" id="daysGrid"></div>

  <div class="actions">
    <button class="btn btn-save" id="btnSave" onclick="salvar()">💾 Salvar Semana</button>
    <button class="btn btn-sec"  id="btnGarmin" onclick="sincronizarGarmin()">📡 Enviar + Sincronizar Garmin</button>
    <button class="btn btn-test" id="btnGenSemana" onclick="gerarProximaSemana()">🤖 Gerar próxima semana</button>
    <button class="btn btn-sec"  id="btnApagarGerados" style="display:none" onclick="apagarTreinosGerados()">🗑 Apagar treinos gerados</button>
    <div id="ftpBtnArea"></div>
  </div>

  <div class="modal-overlay" id="ftpModal" onclick="fecharFTPModal(event)">
    <div class="modal" style="max-width:380px" onclick="event.stopPropagation()">
      <button class="modal-close" onclick="fecharFTPModal()">✕</button>
      <div class="modal-head"><h3>⚡ Criar Teste FTP no Garmin</h3></div>
      <div class="modal-body" style="padding:20px">
        <p style="margin-bottom:14px;color:#444;font-size:.93rem">
          Cria o protocolo completo de teste FTP com os passos corretos no Garmin Connect
          (aquecimento, acelerações, 20min de teste e desaquecimento).
        </p>
        <label style="font-size:.85rem;font-weight:600;display:block;margin-bottom:6px">Data do teste</label>
        <input type="date" id="ftpData" style="padding:9px 10px;border:1.5px solid #ddd;border-radius:7px;font-size:1rem;width:100%;box-sizing:border-box;margin-bottom:16px">
        <div style="display:flex;gap:16px;margin-bottom:4px">
          <label style="display:flex;align-items:center;gap:6px;font-size:.9rem;cursor:pointer">
            <input type="radio" name="ftpModo" id="ftpIndoor" value="indoor" checked> 🏠 Indoor (watts)
          </label>
          <label style="display:flex;align-items:center;gap:6px;font-size:.9rem;cursor:pointer">
            <input type="radio" name="ftpModo" id="ftpOutdoor" value="outdoor"> 🌳 Outdoor (FC)
          </label>
        </div>
        <div id="ftpStatus" style="margin-top:12px;font-size:.85rem;color:#1565c0;min-height:20px"></div>
        <button onclick="confirmarCriarFTP()" style="margin-top:16px;width:100%;padding:12px;background:#7c3aed;color:#fff;border:none;border-radius:8px;font-size:1rem;font-weight:600;cursor:pointer">
          📡 Criar e enviar ao Garmin
        </button>
      </div>
    </div>
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
window.FTP_ON      = {{FTP_ON}};
window.GARMIN_ON   = {{GARMIN_ON}};
window.DIAS_FTP    = {{DIAS_FTP}};
window.ZONAS_POT   = {{ZONAS_POT}};
window.ZONAS_FC    = {{ZONAS_FC}};
const DIAS  = ['Segunda','Terça','Quarta','Quinta','Sexta','Sábado','Domingo'];
const TIPOS = [
  {v:'DESCANSO',    l:'🛌 Descanso',    s:'Descanso'},
  {v:'Z2_LONGO',   l:'🚴 Z2 Longo',    s:'Z2 Longo'},
  {v:'TIROS',      l:'⚡ Tiros',        s:'Tiros'},
  {v:'VO2MAX',     l:'🔥 VO2Max',       s:'VO2Max'},
  {v:'TEMPO',      l:'💨 Tempo',        s:'Tempo'},
  {v:'FORCA',      l:'💪 Força (bike)',  s:'Força Bike'},
  {v:'ACADEMIA',   l:'🏋️ Academia',     s:'Academia'},
  {v:'RECUPERACAO',l:'🌿 Recuperação',  s:'Recuperação'},
  {v:'TESTE_FTP',  l:'⚡ Teste FTP',    s:'Teste FTP'},
];

// Zona de potência principal por tipo de treino (índice Coggan 1-7)
const TIPO_ZONA_POT = {
  RECUPERACAO: 1, Z2_LONGO: 2, TEMPO: 3, FORCA: 3,
  TIROS: 5, VO2MAX: 5, TESTE_FTP: 4,
};

function _alvoPotencia(tipo) {
  const zp = window.ZONAS_POT;
  if (!window.FTP_ON || !zp || !zp.zonas) return null;
  const zonaNum = TIPO_ZONA_POT[tipo];
  if (!zonaNum) return null;
  const z = zp.zonas.find(zz => zz.zona === zonaNum);
  if (!z) return null;
  const range = z.min === 0 ? `até ${z.max}W` : z.max >= 9999 ? `>${z.min}W` : `${z.min}–${z.max}W`;
  return `${range} (Z${zonaNum})`;
}

let monday = getMonday(new Date());
const _resultados = {};
const _planejado = {};
// Estado do checklist de academia por dia: {itens_feitos: [i], sensacao: 1-5}.
const _execucao = {};
const SENSACAO_EMOJI = {1:'😞', 2:'😕', 3:'😐', 4:'🙂', 5:'😄'};
const SENSACAO_TXT   = {1:'muito ruim', 2:'ruim', 3:'normal', 4:'bem', 5:'muito bem'};

// Objetivo e dica por tipo de treino. A prescrição concreta (séries×tempo,
// cadência, recuperação) vem SÓ das "Notas do treino" — texto real gerado por
// dia/prova. Nada de estrutura fixa por tipo aqui: era um template genérico que
// divergia das notas (a IA varia reps/tempo por semana) e confundia o atleta.
const ESPEC_TREINO = {
  Z2_LONGO: {
    obj: 'Base aeróbica. Constrói resistência e melhora a queima de gordura mantendo esforço controlado.',
    dica: 'Cadência 85–95 rpm e FC estável. Sem picos — se subir para Z3, alivie.',
  },
  TEMPO: {
    obj: 'Esforço de limiar. Eleva a capacidade de sustentar um ritmo forte por mais tempo.',
    dica: 'Esforço moderado-alto sustentável. Respiração ritmada, ainda sob controle.',
  },
  FORCA: {
    obj: 'Força específica na bike. Recruta mais fibras musculares pedalando com cadência baixa e marcha pesada.',
    dica: 'Marcha pesada, empurre o pedal. Sente o trabalho nas pernas, não no fôlego.',
  },
  TIROS: {
    obj: 'Tiros neuromusculares. Desenvolve potência e velocidade máxima de pedalada.',
    dica: 'Cada tiro é all-out, do início ao fim. Recupere bem antes do próximo.',
  },
  VO2MAX: {
    obj: 'VO2max. Eleva o teto cardiorrespiratório — o maior estímulo para a performance.',
    dica: 'Os blocos doem. O objetivo é manter a Z5 do primeiro ao último bloco.',
  },
  RECUPERACAO: {
    obj: 'Recuperação ativa. Acelera a regeneração sem gerar fadiga adicional.',
    dica: 'Bem leve mesmo. Se a FC subir, reduza o ritmo. É descanso, não treino.',
  },
  TESTE_FTP: {
    obj: 'Teste de FTP (Functional Threshold Power). Mede a potência máxima que você sustenta por ~1h. Resultado × 0,95 = novo FTP.',
    dica: 'Saída CONTROLADA nos primeiros 3 min. Aumente gradualmente. Pedal leve em Z1 durante os 3 min de desaquecimento ao final.',
  },
};

// Gráfico de estrutura do treino (estilo TrainingPeaks): rampa sequencial de uma
// só cor (leve → intenso) por zona 1-5, validada p/ contraste e distinção CVD.
const TC_ZONA_CORES = ['#8fe0d0', '#5fc3b0', '#37ab97', '#1f8e7d', '#0f7365'];
const TC_FASE_LABEL = {warmup: 'Aquecimento', interval: 'Intervalo', recovery: 'Recuperação', cooldown: 'Volta à calma', rest: 'Descanso'};

function _tcFormatDur(s) {
  const m = Math.floor(s / 60), r = s % 60;
  return r ? `${m}min${r}s` : `${m}min`;
}

function renderGraficoTreino(containerId, dados) {
  const el = document.getElementById(containerId);
  if (!el) return;
  const segs = (dados && dados.segments) || [];
  if (!segs.length) { el.innerHTML = '<div class="tc-empty">Sem estrutura detalhada para este treino.</div>'; return; }

  const barsHtml = segs.map(s => {
    const zona = Math.min(Math.max(s.zona || 1, 1), 5);
    const cor = TC_ZONA_CORES[zona - 1];
    const alturaPct = 24 + (zona - 1) * 19;
    const faseLabel = TC_FASE_LABEL[s.fase] || s.fase;
    const faixa = (s.min != null && s.max != null) ? `${s.min}–${s.max} ${s.unidade}` : `Zona ${zona}`;
    return `<div class="tc-bar" style="height:${alturaPct}%;flex:${s.duracao_s} 0 0;background:${cor}" tabindex="0">`
         + `<div class="tc-tip"><b>${faseLabel}</b> · ${_tcFormatDur(s.duracao_s)}<br>${faixa}</div>`
         + `</div>`;
  }).join('');

  el.innerHTML = `
    <div class="tc-bars">${barsHtml}</div>
    <div class="tc-axis"><span>0:00</span><span>${_tcFormatDur(dados.total_s || 0)}</span></div>
    <div class="tc-legend">
      <span>Leve</span>
      ${TC_ZONA_CORES.map(c => `<span class="tc-sw" style="background:${c}"></span>`).join('')}
      <span>Intenso</span>
    </div>`;
}

async function carregarGraficoTreino(key, tipo, duracaoMin, indoor, descricao) {
  const containerId = `tc-${key}`;
  try {
    // A descrição vai junto: o desenho é montado em cima da prescrição que está
    // logo abaixo dele ("3×15 min" desenha 3 blocos, não os 5 do molde do tipo).
    const desc = (descricao || '').slice(0, 1200);
    const r = await fetch(`/workout/estrutura/${tipo}?duracao_min=${Math.round(duracaoMin)}&indoor=${indoor}`
                          + (desc ? `&descricao=${encodeURIComponent(desc)}` : ''));
    if (!r.ok) throw new Error('falhou');
    const dados = await r.json();
    renderGraficoTreino(containerId, dados);
  } catch (e) {
    const el = document.getElementById(containerId);
    if (el) el.innerHTML = '<div class="tc-empty">Não consegui carregar o gráfico.</div>';
  }
}

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

function _parseAcademiaTexto(descricao) {
  const raw = (descricao || '').replace(/</g, '&lt;');
  const lines = raw.split('\\n');

  const focoM = lines[0] ? lines[0].match(/\\(foco:\\s*([^)]+)\\)/i) : null;
  const foco = focoM ? focoM[1] : '';

  let porqueText = '', obsText = '', section = '';
  const exItens = [];

  for (let i = 1; i < lines.length; i++) {
    const l = lines[i].trim();
    if (!l) continue;
    if (l.indexOf('POR QUE HOJE:') === 0) { section = 'porque'; porqueText = l.slice(13).trim(); continue; }
    if (l.indexOf('EXERC') === 0 && l.indexOf(':') > 0) { section = 'ex'; continue; }
    if (l.indexOf('OBSERVA') === 0 && l.indexOf(':') > 0) { section = 'obs'; continue; }
    if (section === 'porque') porqueText += ' ' + l;
    else if (section === 'ex') exItens.push(l);
    else if (section === 'obs') obsText += (obsText ? ' · ' : '') + l.replace(/^-\\s*/, '');
  }

  return {raw, foco, porqueText: porqueText.trim(), obsText, exItens};
}

const PERIODO_LABEL = {manha: '🌅 Manhã', meio_dia: '☀️ Meio-dia', tarde: '🌇 Tarde', noite: '🌙 Noite'};

// Card de academia do DIA DUPLO (bike + gym). Com `key`, ele é interativo: o
// mesmo checklist do dia só-academia, mas gravando no sub-objeto. Sem `key`
// (prévia da semana gerada) fica só leitura.
function renderAcademiaBloco(ac, key, locked) {
  const ad = ac.duracao_min || 0;
  const adStr = ad ? ((Math.floor(ad/60)>0?Math.floor(ad/60)+'h':'')+(ad%60>0?ad%60+'min':'')) : '';
  const {raw, foco, porqueText, obsText, exItens} = _parseAcademiaTexto(ac.descricao);
  const clickable = !!key;
  const sk = key ? key + '-ac' : '';
  const interativo = clickable && exItens.length > 0;
  if (interativo) {
    _execucao[sk] = Object.assign({data: key, itens_feitos: [], cargas: {}, sensacao: null},
                                  ac.execucao || {});
  }

  let detalhes = '';
  if (porqueText) detalhes += '<div class="ac-porque">' + porqueText + '</div>';
  if (interativo) {
    // stopPropagation: o card inteiro é um acordeão com onclick — sem isto,
    // marcar um exercício fecharia o bloco na cara do atleta.
    detalhes += '<div class="ac-check" onclick="event.stopPropagation()">'
              + renderChecklistAcademia(sk, exItens, !!locked) + '</div>';
  } else if (exItens.length) {
    detalhes += '<ul class="ac-exercicios">';
    for (let i = 0; i < exItens.length; i++) detalhes += '<li>' + exItens[i] + '</li>';
    detalhes += '</ul>';
  } else {
    detalhes += '<div class="ac-obs">' + (raw.replace(/\\n/g, '<br>')) + '</div>';
  }
  if (obsText) detalhes += '<div class="ac-obs">&#128204; ' + obsText + '</div>';

  const classes = 'academia-bloco' + (clickable ? ' clickable' : ' expanded');
  const onclick = clickable ? ` onclick="this.classList.toggle('expanded')"` : '';
  let html = `<div class="${classes}"${onclick}>`;
  html += '<div class="ac-header"><span class="ac-titulo">🏋️ Academia</span>';
  if (adStr) html += '<span class="ac-dur">&#8987; ' + adStr + '</span>';
  if (clickable) html += '<span class="ac-arrow">&#9656;</span>';
  html += '</div>';
  if (ac.periodo && PERIODO_LABEL[ac.periodo]) html += '<div class="ac-foco">' + PERIODO_LABEL[ac.periodo] + '</div>';
  if (foco) html += '<div class="ac-foco">Foco: ' + foco + '</div>';
  html += '<div class="ac-detalhes">' + detalhes + '</div>';
  html += '</div>';
  return html;
}

// Academia não tem Garmin: quem registra a sessão é o próprio atleta, marcando
// os exercícios conforme executa. A nota de sensação (1-5) é o "enviar" — é ela
// que fecha a sessão e dispara o registro do realizado no servidor.
// "1. Agachamento — 3x10 — 20 kg (força de quadríceps)" → principal + detalhe.
// O "porquê" entre parênteses vira uma segunda linha menor: junto do nome ele
// empurrava tudo e quebrava o texto em palavras soltas na coluna estreita.
function _splitExercicio(txt) {
  const s = String(txt || '').trim();
  const m = s.match(/^(.*?)\s*\(([^()]*)\)\s*$/);
  return m ? {principal: m[1].trim(), detalhe: m[2].trim()} : {principal: s, detalhe: ''};
}

// `sk` (slot key) identifica o checklist no DOM e em _execucao. Um dia duplo tem
// dois: o do treino principal (sk = data) e o do bloco de academia
// (sk = data + '-ac'). A data real do treino vem de _execucao[sk].data, porque é
// ela que monta a URL — o sk sozinho não serve.
function renderChecklistAcademia(sk, itens, locked) {
  const exec = _execucao[sk] || {};
  const feitos = new Set(exec.itens_feitos || []);
  const cargas = exec.cargas || {};
  const sens = exec.sensacao || null;
  const dis = locked ? 'disabled' : '';
  const key = sk;

  let html = `<div class="ex-progresso" id="ex-prog-${key}">${feitos.size}/${itens.length} concluídos</div>`;
  html += `<div class="ex-check-list" id="ex-list-${key}">`;
  for (let i = 0; i < itens.length; i++) {
    const on = feitos.has(i);
    const kg = cargas[String(i)] ?? '';
    const ex = _splitExercicio(itens[i]);
    // Nome e carga em LINHAS separadas: lado a lado não cabe na largura de uma
    // coluna do calendário. O input fica FORA do <label> porque, dentro dele,
    // tocar no campo marcaria o checkbox junto.
    html += `<div class="ex-check-item${on ? ' feito' : ''}" id="ex-item-${key}-${i}">
      <label class="ex-check-main">
        <input type="checkbox" ${on ? 'checked' : ''} ${dis} onchange="toggleExercicio('${key}',${i},this.checked)">
        <span class="ex-nome">
          <span class="ex-principal">${ex.principal}</span>
          ${ex.detalhe ? `<span class="ex-detalhe">${ex.detalhe}</span>` : ''}
        </span>
      </label>
      <div class="ex-carga">
        <span>carga</span>
        <input type="number" min="0" max="500" step="0.5" inputmode="decimal" value="${kg}"
          placeholder="—" title="Carga que você usou neste exercício" ${dis}
          onchange="setCarga('${key}',${i},this.value)">
        <span>kg</span>
      </div>
    </div>`;
  }
  html += '</div>';

  html += `<div class="sensacao-box">
    <label>Como se sentiu?</label>
    <div class="sensacao-btns" id="sens-${key}">
      ${[1,2,3,4,5].map(n => `<button ${dis} class="${sens === n ? 'ativo' : ''}"
        onclick="darSensacao('${key}',${n})" title="${SENSACAO_TXT[n]}">${SENSACAO_EMOJI[n]}</button>`).join('')}
    </div>
    <div class="sensacao-sel" id="sens-sel-${key}">${sens ? SENSACAO_TXT[sens] : ''}</div>
    <div class="ex-msg" id="ex-msg-${key}"></div>
  </div>`;
  return html;
}

// Carga registrada por exercício. É o número que a IA usa para prescrever a
// próxima sessão — sem ele a progressão de força vira chute.
function setCarga(key, idx, valor) {
  const e = _execucao[key] || (_execucao[key] = {data: key, itens_feitos: [], sensacao: null});
  e.cargas = e.cargas || {};
  const kg = parseFloat(String(valor).replace(',', '.'));
  if (isNaN(kg) || kg <= 0) delete e.cargas[String(idx)];
  else e.cargas[String(idx)] = kg;
  enviarExecucao(key, e.sensacao);
}

function toggleExercicio(key, idx, on) {
  const e = _execucao[key] || (_execucao[key] = {data: key, itens_feitos: [], sensacao: null});
  const s = new Set(e.itens_feitos || []);
  on ? s.add(idx) : s.delete(idx);
  e.itens_feitos = [...s].sort((a, b) => a - b);

  document.getElementById(`ex-item-${key}-${idx}`)?.classList.toggle('feito', on);
  const total = document.querySelectorAll(`#ex-list-${key} .ex-check-item`).length;
  const prog = document.getElementById(`ex-prog-${key}`);
  if (prog) prog.textContent = `${e.itens_feitos.length}/${total} concluídos`;

  enviarExecucao(key, e.sensacao);
}

function darSensacao(key, n) {
  const e = _execucao[key] || (_execucao[key] = {data: key, itens_feitos: [], sensacao: null});
  e.sensacao = n;
  document.querySelectorAll(`#sens-${key} button`).forEach((b, i) => b.classList.toggle('ativo', i + 1 === n));
  const sel = document.getElementById(`sens-sel-${key}`);
  if (sel) sel.textContent = SENSACAO_TXT[n] || '';
  enviarExecucao(key, n);
}

async function enviarExecucao(key, sensacao) {
  const e = _execucao[key] || {itens_feitos: []};
  const dataISO = e.data || key;   // no bloco de academia o sk tem sufixo '-ac'
  const msg = document.getElementById(`ex-msg-${key}`);
  const setMsg = (txt, cor) => { if (msg) { msg.style.color = cor; msg.textContent = txt; } };
  setMsg('⏳ salvando…', 'var(--muted)');
  try {
    const r = await fetch(`/workout/treino/${iso(monday)}/${dataISO}/academia-execucao`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        itens_feitos: e.itens_feitos || [],
        cargas: e.cargas || {},
        sensacao: sensacao ?? null,
      }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || 'Erro');

    if (d.erro)            setMsg(d.erro, '#c62828');
    else if (d.registrado) {
      setMsg(d.nota != null ? `✅ sessão registrada — nota ${d.nota}` : '✅ sessão registrada', '#2e7d32');
      toast('✅ Academia registrada!', 'ok');
      await load();   // recarrega para o card virar "realizado" e mostrar a avaliação
    }
    // Dia duplo: o `resultado` do dia é do pedal, que ainda vem pelo Garmin.
    // A academia fica guardada no bloco e alimenta a progressão de carga.
    else if (d.dia_duplo && sensacao != null) {
      setMsg('✅ academia concluída', '#2e7d32');
      toast('✅ Academia concluída!', 'ok');
    }
    else setMsg('progresso salvo', 'var(--muted)');
  } catch (err) {
    setMsg('não salvou: ' + err.message, '#c62828');
  }
}

function toggleDescEdit(key) {
  const ta = document.getElementById(`desc-${key}`);
  if (!ta) return;
  ta.style.display = ta.style.display === 'none' ? '' : 'none';
  if (ta.style.display !== 'none') ta.focus();
}

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
  // Agrupa por data — pode haver mais de um treino no mesmo dia (o principal
  // + "extras" adicionados manualmente, origem="extra"). O principal é a
  // primeira entrada não-extra da data; extras nunca substituem o principal.
  const map = {};
  const extrasMap = {};
  (treinos||[]).forEach(t => {
    if (t.origem === 'extra') {
      (extrasMap[t.data] = extrasMap[t.data] || []).push(t);
    } else if (!map[t.data]) {
      map[t.data] = t;
    }
  });
  const todayISO = localIso(new Date());

  for (let i = 0; i < 7; i++) {
    const d   = addDays(monday, i);
    const key = iso(d);
    const t   = map[key] || {data: key, tipo:'DESCANSO'};
    const extras = extrasMap[key] || [];
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

    _planejado[key] = {tipo: t.tipo, duracao_min: t.duracao_min, cadencia_rpm: t.cadencia_rpm, descricao: t.descricao, academia: t.academia || null, indoor: t.indoor || false};
    const res = t.resultado || null;
    if (res) _resultados[key] = res;
    const resHTML = res
      ? `<button class="aval-btn" onclick="abrirAvaliacao('${key}')">📊 Ver avaliação do treino</button>`
      : '';

    const isAcademia = t.tipo === 'ACADEMIA';
    const cadReal    = (res && res.cadencia_media_rpm) ? res.cadencia_media_rpm : '';
    const avgPowReal = (res && res.avg_power) ? res.avg_power : null;
    const tssObtido    = res ? res.tss_obtido : null;
    const tssPlanejado = t.tss_planejado || null;
    const tssMetric  = tssObtido || tssPlanejado;
    const metricsHTML = (dur || dist || elev || cadReal || avgPowReal || tssMetric)
      ? `<div class="metrics" id="metrics-${key}">
           ${dur  ? `<div class="metric"><div class="mv">${dur} min</div><div class="ml">Duração</div></div>` : ''}
           ${tssMetric ? `<div class="metric"><div class="mv">${tssMetric} TSS</div><div class="ml">${tssObtido ? 'TSS' : 'TSS previsto'}</div></div>` : ''}
           ${!isAcademia && cadReal ? `<div class="metric"><div class="mv">${cadReal} rpm</div><div class="ml">Cad. real</div></div>` : ''}
           ${!isAcademia && avgPowReal ? `<div class="metric"><div class="mv">${avgPowReal}W</div><div class="ml">Potência</div></div>` : ''}
           ${dist ? `<div class="metric"><div class="mv">${dist} km</div><div class="ml">Distância</div></div>` : ''}
           ${elev ? `<div class="metric"><div class="mv">${elev} m</div><div class="ml">Elevação</div></div>` : ''}
         </div>`
      : `<div id="metrics-${key}"></div>`;

    const durStr = dur ? (() => { const h = Math.floor(dur/60); const m = dur%60; return (h>0?h+'h':'')+( m>0?m+'min':''); })() : '';
    const potAlvo = (!hide && !isAcademia) ? _alvoPotencia(t.tipo) : null;
    const resumoHTML = !hide ? `
      <ul class="treino-resumo" id="resumo-${key}">
        <li><span class="ri">⏱</span><span class="rk">Tempo</span><span class="rv" id="resumo-dur-${key}">${durStr || '—'}</span></li>
        ${!isAcademia ? `<li><span class="ri">🦵</span><span class="rk">Cad. alvo</span><span class="rv rv-cad" id="resumo-cad-${key}">${cad ? cad+' rpm' : '—'}</span></li>` : ''}
        ${potAlvo ? `<li id="resumo-alvo-${key}" style="${!t.indoor ? 'display:none' : ''}"><span class="ri">⚡</span><span class="rk">Alvo indoor</span><span class="rv">${potAlvo}</span></li>` : ''}
        ${tssPlanejado ? `<li><span class="ri">📊</span><span class="rk">P: TSS</span><span class="rv">${tssPlanejado}${tssObtido ? ` · real ${tssObtido}` : ''}</span></li>` : ''}
      </ul>` : '';

    // Dia que a IA reorganizou: no modo automático o plano muda sozinho, então o
    // card precisa dizer o que era antes e por quê — senão o atleta abre a semana
    // e não reconhece o próprio treino.
    const aj = t.ajuste_ia;
    const ajusteHTML = (aj && !hide) ? `
      <div class="ajuste-ia" title="Ajuste automático do treinador">
        <b>🔄 Ajustado</b>${aj.antes && aj.antes.tipo ? ` — era ${(TIPOS.find(tp => tp.v === aj.antes.tipo) || {l: aj.antes.tipo}).l}` : ''}
        ${aj.motivo ? `<div class="ai-motivo">${aj.motivo.replace(/</g,'&lt;')}</div>` : ''}
      </div>` : '';

    const acSub = t.academia;
    const academiaSubHTML = acSub && acSub.descricao
      ? renderAcademiaBloco(acSub, key, key > todayISO) : '';

    // Dia de academia com lista no formato da casa vira checklist. Descrição
    // em texto livre (plano antigo, editado à mão) cai no textarea de sempre.
    const exItensAcad = isAcademia ? _parseAcademiaTexto(desc).exItens : [];
    const temChecklist = exItensAcad.length > 0;
    if (temChecklist) {
      _execucao[key] = Object.assign({data: key, itens_feitos: [], cargas: {}, sensacao: null},
                                     t.execucao || {});
    }
    // O checklist é execução, não edição do plano: `isFuturo` inclui HOJE (para
    // travar a prescrição contra edição manual), mas hoje é exatamente quando o
    // atleta está na academia marcando. Só dia que ainda não chegou fica travado.
    const checkTravado = key > todayISO;

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
          ${ajusteHTML}
          ${resumoHTML}
          ${metricsHTML}

          <div>
            <div class="notas-head">
              <label>${isAcademia ? 'Exercícios' : 'Notas'}</label>
              <button class="info-treino" onclick="abrirTreinoInfo('${key}')" title="Ver especificação do treino"><span class="ic">ⓘ</span> saber mais</button>
            </div>
            ${temChecklist ? renderChecklistAcademia(key, exItensAcad, checkTravado) : ''}
            <textarea id="desc-${key}" placeholder="${isAcademia ? 'Lista de exercícios...' : 'Detalhes...'}" ${lockAttr} style="${temChecklist ? 'display:none' : ''}">${desc}</textarea>
            ${temChecklist && !lockAttr ? `<button class="ex-edit-toggle" onclick="toggleDescEdit('${key}')">✏️ editar a lista</button>` : ''}
          </div>
        </div>

        <div id="rest-${key}" style="${hide ? '' : 'display:none'}">
          <div class="rest-badge"><span class="icon">😴</span>Dia de descanso</div>
        </div>
        ${!isFuturo ? `<button class="rest-toggle" id="resttoggle-${key}" onclick="toggleRest('${key}')">
          ${hide ? '🏃 Adicionar treino' : '🛌 Marcar descanso'}
        </button>` : ''}

        ${window.FTP_ON && !hide && !isAcademia ? `<div class="indoor-area">
          <div class="indoor-toggle" id="indoor-toggle-${key}">
            <button id="indoor-out-${key}" class="${!t.indoor ? 'ativo' : ''}"
              onclick="setIndoor('${key}', false)" title="Outdoor — Garmin usará frequência cardíaca">
              🚵 Outdoor (FC)
            </button>
            <button id="indoor-in-${key}" class="${t.indoor ? 'ativo' : ''}"
              onclick="setIndoor('${key}', true)" title="Indoor — Garmin usará watts do rolo">
              🏠 Indoor (Watts)
            </button>
          </div>
          <div class="indoor-sync-msg" id="indoor-msg-${key}"></div>
        </div>` : ''}
        ${window.NUTRICAO_ON ? `<div class="nutri-area">
          <button class="nutri-toggle" onclick="abrirNutriModal('${key}')">
            🥗 Plano alimentar do dia
          </button>
        </div>` : ''}
        ${resHTML}
      </div>`;

    const dayCol = document.createElement('div');
    dayCol.className = 'day-col';
    dayCol.appendChild(c);
    if (academiaSubHTML) {
      const acWrap = document.createElement('div');
      acWrap.innerHTML = academiaSubHTML;
      dayCol.appendChild(acWrap.firstElementChild);
    }
    extras.forEach(ex => {
      const wrap = document.createElement('div');
      wrap.innerHTML = renderExtraCard(ex, key);
      dayCol.appendChild(wrap.firstElementChild);
    });
    grid.appendChild(dayCol);
  }
}

function extraTipoLabel(tipo) {
  return (TIPOS.find(tp => tp.v === tipo) || {l: tipo}).l;
}

function extraTipoOpts(selecionado) {
  return TIPOS.filter(tp => tp.v !== 'DESCANSO').map(tp =>
    `<option value="${tp.v}" ${tp.v === selecionado ? 'selected' : ''}>${tp.l}</option>`
  ).join('');
}

function renderExtraCard(t, key) {
  const id = t.id;
  const dur = t.duracao_min || '';
  const durStr = dur ? ((Math.floor(dur/60)>0?Math.floor(dur/60)+'h':'')+(dur%60>0?dur%60+'min':'')) : '';
  const tss = t.tss_planejado || '';
  const desc = (t.descricao || '').replace(/</g, '&lt;');
  const checked = t.concluido ? 'checked' : '';
  return `<div class="extra-card" id="extra-${id}">
    <div class="extra-head">
      <span class="extra-chip tipo-${t.tipo}">${extraTipoLabel(t.tipo)}</span>
      <button class="extra-remove" onclick="removerExtra('${key}','${id}')" title="Remover">✕</button>
    </div>
    <div class="extra-body">
      ${(durStr || tss) ? `<div class="extra-meta">
        ${durStr ? `<span>⏱ ${durStr}</span>` : ''}
        ${tss ? `<span>⚡ ${tss} TSS</span>` : ''}
      </div>` : ''}
      ${desc ? `<div class="extra-desc">${desc}</div>` : ''}
      <label class="extra-check">
        <input type="checkbox" ${checked} onchange="toggleExtraConcluido('${key}','${id}', this.checked)"> Concluído
      </label>
      <button class="extra-edit-toggle" onclick="toggleExtraEditForm('${id}')">✏️ Editar</button>
      <div class="extra-form" id="extra-edit-form-${id}" style="display:none">
        <select id="ee-tipo-${id}">${extraTipoOpts(t.tipo)}</select>
        <input type="number" id="ee-dur-${id}" placeholder="Duração (min)" value="${dur}">
        <textarea id="ee-desc-${id}" placeholder="Notas...">${desc}</textarea>
        <div class="extra-form-actions">
          <button class="ef-save" onclick="salvarEdicaoExtra('${key}','${id}')">Salvar</button>
          <button class="ef-cancel" onclick="toggleExtraEditForm('${id}')">Cancelar</button>
        </div>
      </div>
    </div>
  </div>`;
}

function toggleExtraEditForm(extraId) {
  const f = document.getElementById(`extra-edit-form-${extraId}`);
  if (f) f.style.display = f.style.display === 'none' ? '' : 'none';
}

async function salvarEdicaoExtra(key, extraId) {
  const tipo   = document.getElementById(`ee-tipo-${extraId}`).value;
  const durRaw = document.getElementById(`ee-dur-${extraId}`).value;
  const desc   = document.getElementById(`ee-desc-${extraId}`).value.trim();
  try {
    const r = await fetch(`/workout/treino/${iso(monday)}/${key}/extra/${extraId}`, {
      method: 'PATCH',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({tipo, duracao_min: durRaw ? parseInt(durRaw) : null, descricao: desc || null}),
    });
    if (!r.ok) throw new Error(await r.text());
    toast('✅ Treino atualizado', 'ok');
    await load();
  } catch(e) {
    toast('❌ Erro: ' + e.message, 'err');
  }
}

async function removerExtra(key, extraId) {
  if (!confirm('Remover este treino?')) return;
  try {
    const r = await fetch(`/workout/treino/${iso(monday)}/${key}/extra/${extraId}`, {method: 'DELETE'});
    if (!r.ok) throw new Error(await r.text());
    toast('🗑️ Treino removido', 'info');
    await load();
  } catch(e) {
    toast('❌ Erro: ' + e.message, 'err');
  }
}

async function toggleExtraConcluido(key, extraId, checked) {
  try {
    const r = await fetch(`/workout/treino/${iso(monday)}/${key}/extra/${extraId}`, {
      method: 'PATCH',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({concluido: checked}),
    });
    if (!r.ok) throw new Error(await r.text());
  } catch(e) {
    toast('❌ Erro: ' + e.message, 'err');
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

async function setIndoor(key, indoor) {
  const btnIn  = document.getElementById(`indoor-in-${key}`);
  const btnOut = document.getElementById(`indoor-out-${key}`);
  const msg    = document.getElementById(`indoor-msg-${key}`);
  if (!btnIn) return;

  btnIn.disabled = true; btnOut.disabled = true;
  msg.textContent = '⏳ Salvando...';

  // extrai semana_inicio da segunda-feira visível
  const semanaInicio = iso(monday);

  try {
    const r = await fetch(`/workout/treino/${semanaInicio}/${key}/indoor`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({indoor}),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || 'Erro');

    btnIn.classList.toggle('ativo', indoor);
    btnOut.classList.toggle('ativo', !indoor);

    if (_planejado[key]) _planejado[key].indoor = indoor;

    const liAlvo = document.getElementById(`resumo-alvo-${key}`);
    if (liAlvo) liAlvo.style.display = indoor ? '' : 'none';

    const label = indoor ? '🏠 Indoor (Watts)' : '🚵 Outdoor (FC)';
    if (d.garmin_sync && d.garmin_sync.ok) {
      msg.textContent = `✅ ${label} — workout re-enviado ao Garmin`;
    } else if (d.garmin_sync) {
      msg.textContent = `✅ ${label} salvo — sem Garmin conectado`;
    } else {
      msg.textContent = `✅ ${label} salvo`;
    }
    setTimeout(() => { if (msg) msg.textContent = ''; }, 4000);
  } catch(e) {
    msg.textContent = '❌ ' + e.message;
  } finally {
    btnIn.disabled = false; btnOut.disabled = false;
  }
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
  // FC marcada como não confiável (cinta sem bateria / sem cinta) continua
  // visível, mas esmaecida e rotulada — o número existe, só não conta na nota.
  const fcOff = !!res.fc_invalida;
  const fcStyle = fcOff ? ' style="opacity:.45"' : '';
  const fcSuf = fcOff ? ' (ignorada)' : '';
  if (res.avg_hr) mItems.push(`<div class="metric"${fcStyle}><div class="mv">${res.avg_hr} bpm</div><div class="ml">FC média${fcSuf}</div></div>`);
  if (res.max_hr) mItems.push(`<div class="metric"${fcStyle}><div class="mv">${res.max_hr} bpm</div><div class="ml">FC máx${fcSuf}</div></div>`);
  if (res.avg_power) mItems.push(`<div class="metric"><div class="mv">${res.avg_power}W</div><div class="ml">Potência média</div></div>`);
  if (res.norm_power) mItems.push(`<div class="metric"><div class="mv">${res.norm_power}W</div><div class="ml">NP (normalizada)</div></div>`);
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

  // Cinta cardíaca: quando a FC não vale (sem bateria, cinta solta, sem cinta),
  // o atleta refaz a avaliação sem FC — a nota deixa de cobrar zona que não foi
  // medida. O mesmo ajuste que ele pode pedir no chat.
  // Sessão contada pelo atleta (academia, pedal sem relógio): nunca houve FC
  // para "voltar a considerar" — o botão só levaria a uma reavaliação pedindo
  // zonas que ninguém mediu. Banner próprio e sem botão.
  const relatada = res.origem === 'relato_atleta';
  const fcBanner = relatada
    ? `<div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:9px;padding:9px 12px;margin-bottom:10px;font-size:.84rem;color:#1e40af">
         🗣️ Sessão <b>registrada pelo seu relato</b> — sem dados de dispositivo, então não há FC, potência nem TSS.
       </div>`
    : fcOff
    ? `<div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:9px;padding:9px 12px;margin-bottom:10px;font-size:.84rem;color:#9a3412">
         ⚠️ Avaliado <b>sem os dados de FC</b>${res.fc_invalida_motivo ? ` — ${res.fc_invalida_motivo}` : ''}.
       </div>`
    : '';
  const relatoHTML = res.relato
    ? `<div class="analise-bloco" style="margin-bottom:10px"><div class="esp-titulo">O que você contou</div>
         <div class="esp-notas">${res.relato.replace(/</g,'&lt;').replace(/\\n/g,'<br>')}</div></div>`
    : '';
  const fcBtn = relatada
    ? ''
    : fcOff
    ? `<button class="aval-btn" id="btnFC-${key}" onclick="marcarFCInvalida('${key}', false)" style="margin-top:10px">↩️ Voltar a considerar a FC</button>`
    : `<button class="aval-btn" id="btnFC-${key}" onclick="marcarFCInvalida('${key}', true)" style="margin-top:10px">⚠️ FC não confiável — reavaliar sem FC</button>`;

  document.getElementById('avalModalHead').innerHTML = `<h3>📊 Avaliação do treino</h3><div class="modal-sub">${lbl}</div>`;
  document.getElementById('avalModalBody').innerHTML = `
    ${fcBanner}
    ${mItems.length ? `<div class="metrics">${mItems.join('')}</div>` : ''}
    ${relatoHTML}
    ${notaHTML}
    <div class="analise-bloco">
      ${ia.resumo ? `<div class="resumo-txt">"${ia.resumo}"</div>` : ''}
      ${fortes ? `<ul class="analise-lista">${fortes}</ul>` : ''}
      ${fracos ? `<ul class="analise-lista" style="margin-top:6px">${fracos}</ul>` : ''}
    </div>
    ${fcBtn}
    <div id="fcMsg-${key}" style="font-size:.83rem;margin-top:8px;color:#6b7280"></div>
    `;
  document.getElementById('avalModal').classList.add('show');
}

async function marcarFCInvalida(key, invalida) {
  const btn = document.getElementById(`btnFC-${key}`);
  const msg = document.getElementById(`fcMsg-${key}`);
  let motivo = '';
  if (invalida) {
    const r = prompt('O que houve com a FC? (ex.: cinta sem bateria)', 'cinta sem bateria');
    if (r === null) return;  // cancelou
    motivo = r.trim();
  }
  btn.disabled = true;
  msg.textContent = '🤖 Refazendo a avaliação…';
  try {
    const r = await fetch(`/workout/treino/${iso(monday)}/${key}/fc-invalida`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({invalida, motivo}),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || 'Erro');
    const res = Object.assign({}, _resultados[key]);
    if (d.analise_ia) res.analise_ia = d.analise_ia;
    res.fc_invalida = d.fc_invalida;
    res.fc_invalida_motivo = d.motivo;
    res.tss_obtido = d.tss_obtido;
    _resultados[key] = res;
    abrirAvaliacao(key);
    const m = document.getElementById(`fcMsg-${key}`);
    if (m) m.textContent = `✅ Avaliação refeita${d.nota != null ? ` — nova nota ${d.nota}` : ''}.`;
    load();
  } catch(e) {
    msg.textContent = '❌ ' + e.message;
    btn.disabled = false;
  }
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
  const isIndoor = p.indoor || false;

  const dt = new Date(key + 'T00:00');
  const diaLabel = `${DIAS[(dt.getDay()+6)%7]} ${key.slice(8,10)}/${key.slice(5,7)}`;
  const meta = [diaLabel];
  if (p.duracao_min) meta.push(`⏱ ${p.duracao_min} min`);
  if (cad && tipo !== 'ACADEMIA') meta.push(`🦵 ${cad} rpm`);

  let corpo = '';

  if (tipo === 'ACADEMIA') {
    // Academia puro: mostra apenas os exercícios (sem estrutura de bike)
    corpo += `<div class="esp-obj">Treino de musculação complementar ao MTB. Exercícios escolhidos pela IA considerando os treinos de bike do dia anterior e posterior.</div>`;
    if (notas && notas.trim()) {
      corpo += `<div class="esp-bloco" style="margin-top:10px"><div class="esp-titulo">Exercícios</div>`
             + `<div class="esp-notas">${notas.replace(/</g,'&lt;').replace(/\\n/g,'<br>')}</div></div>`;
    } else {
      corpo += `<div class="esp-obj" style="margin-top:8px">Exercícios ainda não definidos — gere a semana com IA.</div>`;
    }
  } else {
    // Treino de bike: objetivo + dica + a prescrição REAL (notas). Não há mais
    // lista "Como executar" fixa por tipo — ela divergia das notas. As "Notas do
    // treino" são a única fonte da prescrição (séries×tempo, cadência, recup).
    const modoLabel = isIndoor ? ' <span style="font-size:.72rem;background:#e3f2fd;color:#1565c0;border-radius:4px;padding:1px 6px;font-weight:700;vertical-align:middle">🏠 Indoor — Watts</span>' : '';
    corpo += `<div class="treino-chart" id="tc-${key}"><div class="tc-loading">Carregando gráfico…</div></div>`;
    // Exporta o treino do dia em .zwo (Zwift Workout) para abrir em Zwift/
    // TrainerRoad/MyWhoosh/Rouvy etc. Potência relativa ao FTP → todo usuário
    // baixa o seu próprio arquivo, mesmo sem FTP configurado.
    corpo += `<a class="erg-dl" href="/workout/zwo/semana/${iso(monday)}/${key}" download title="Baixar treino para rolo/home trainer (Zwift, TrainerRoad…)">⬇ Baixar treino (.zwo)</a>`;
    if (esp) {
      corpo += `<div class="esp-obj">${esp.obj}</div>`;
      // Cadência da dica vem do treino (não fixa) — evita divergir do header/notas.
      let dica = esp.dica;
      if (cad) dica = dica.replace(/\\d{2,3}\\s*[–-]\\s*\\d{2,3}\\s*rpm/gi, `${cad} rpm`);
      corpo += `<div class="esp-dica">💡 ${dica}</div>`;
    }
    if (notas && notas.trim()) {
      corpo += `<div class="esp-bloco" style="margin-top:14px"><div class="esp-titulo">Notas do treino${modoLabel}</div>`
             + `<div class="esp-notas">${notas.replace(/</g,'&lt;').replace(/\\n/g,'<br>')}</div></div>`;
    }
    // O treino de academia do dia (se houver) tem seu próprio bloco/card no
    // calendário, que expande com clique — ver renderAcademiaBloco().
  }

  if (!corpo) corpo = `<div class="esp-obj">Sem especificação detalhada para este treino.</div>`;

  document.getElementById('treinoModalHead').innerHTML = `<h3>${tipoInfo.l}</h3><div class="modal-sub">${meta.join('  ·  ')}</div>`;
  document.getElementById('treinoModalBody').innerHTML = corpo;
  document.getElementById('treinoModal').classList.add('show');

  if (tipo !== 'ACADEMIA') {
    carregarGraficoTreino(key, tipo, p.duracao_min || 60, isIndoor, notas);
  }
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

function abrirModalFTP() {
  const inp = document.getElementById('ftpData');
  // Pré-preenche com amanhã usando hora local (evita desvio de fuso UTC)
  const h = new Date();
  const amanha = new Date(h.getFullYear(), h.getMonth(), h.getDate() + 1);
  const mm = String(amanha.getMonth() + 1).padStart(2, '0');
  const dd = String(amanha.getDate()).padStart(2, '0');
  inp.value = `${amanha.getFullYear()}-${mm}-${dd}`;
  document.getElementById('ftpStatus').textContent = '';
  document.getElementById('ftpModal').classList.add('show');
}

function fecharFTPModal(e) {
  if (!e || e.target === document.getElementById('ftpModal'))
    document.getElementById('ftpModal').classList.remove('show');
}

async function confirmarCriarFTP() {
  const data = document.getElementById('ftpData').value;
  const indoor = document.getElementById('ftpIndoor').checked;  // radio: indoor selecionado
  const st = document.getElementById('ftpStatus');
  if (!data) { st.textContent = 'Informe a data.'; st.style.color = '#c62828'; return; }
  st.style.color = '#1565c0';
  st.textContent = 'Enviando para o Garmin…';
  try {
    const r = await fetch('/workout/criar-ftp', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({data, duracao_min: 62, forcar_indoor: indoor}),
    });
    if (!r.ok) throw new Error(await r.text());
    const d = await r.json();
    document.getElementById('ftpModal').classList.remove('show');
    toast(`⚡ Teste FTP criado no Garmin para ${data}!`, 'ok');
    window.DIAS_FTP = 0;
    renderFTPBtn();
    await load();
  } catch(e) {
    st.style.color = '#c62828';
    st.textContent = 'Erro: ' + e.message;
  }
}

document.addEventListener('keydown', e => { if (e.key === 'Escape') { fecharNutriModal(); fecharAvalModal(); fecharGenModal(); fecharFTPModal({}); } });

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
      const acSub = (_planejado[key] || {}).academia;
      if (acSub)   t.academia = acSub;
    }
    treinos.push(t);
  }
  return treinos;
}

async function load() {
  updateLabel();
  carregarAdaptacaoPendente();
  try {
    const r = await fetch(`/workout/semana/${iso(monday)}`);
    const d = await r.json();
    document.getElementById('objetivo').value = d.objetivo || '';
    buildCards(d.treinos || []);
    _atualizarBotaoProximaSemana(d.treinos || [], d.proxima_semana_gerada);
    _atualizarBotoesNovato(d);
  } catch {
    buildCards([]);
    _atualizarBotaoProximaSemana([], false);
    _atualizarBotoesNovato({treinos: []});
  }
}

// Ajuste da semana esperando o aceite (só aparece para quem escolheu "quero dar
// o aceite" no perfil; no modo automático a semana já vem ajustada).
const _AD_TIPO_LABEL = {Z2_LONGO:'Z2 longo', RECUPERACAO:'Recuperação', TEMPO:'Tempo',
  FORCA:'Força', TIROS:'Tiros', VO2MAX:'VO2máx', TESTE_FTP:'Teste de FTP',
  ACADEMIA:'Academia', DESCANSO:'Descanso'};

async function carregarAdaptacaoPendente() {
  const painel = document.getElementById('adapPanel');
  if (!painel) return;
  try {
    const r = await fetch('/workout/adaptacao/pendente');
    const d = await r.json();
    const p = d.pendente;
    if (!p || !(p.ajustes || []).length) { painel.innerHTML = ''; return; }
    const itens = p.ajustes.map(a => {
      const dur = a.duracao_min ? ` · ${a.duracao_min} min` : '';
      const motivo = a.motivo ? `<br><span class="ad-motivo">${a.motivo}</span>` : '';
      return `<li><b>${a.data.slice(8,10)}/${a.data.slice(5,7)}</b>: ${_AD_TIPO_LABEL[a.tipo] || a.tipo}${dur}${motivo}</li>`;
    }).join('');
    painel.innerHTML = `<div class="adap-panel">
      <h4>🔄 Sugestão de ajuste na semana</h4>
      ${p.resumo ? `<div class="ad-resumo">${p.resumo}</div>` : ''}
      <ul>${itens}</ul>
      <button class="ad-ok" onclick="responderAdaptacao(true)">Aplicar</button>
      <button class="ad-no" onclick="responderAdaptacao(false)">Manter o plano</button>
      <span id="adapMsg" style="font-size:.85rem;margin-left:8px"></span>
    </div>`;
  } catch { painel.innerHTML = ''; }
}

async function responderAdaptacao(aceitar) {
  const msg = document.getElementById('adapMsg');
  if (msg) msg.textContent = aceitar ? 'Aplicando…' : 'Descartando…';
  try {
    const r = await fetch('/workout/adaptacao/pendente', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({aceitar}),
    });
    if (!r.ok) throw new Error('falhou');
    document.getElementById('adapPanel').innerHTML = '';
    load();
  } catch { if (msg) msg.textContent = '❌ não consegui, tente de novo'; }
}

function _temTreinoReal(treinos) {
  return (treinos || []).some(t => t.tipo !== 'DESCANSO' && t.duracao_min);
}

function _atualizarBotoesNovato(d) {
  const treinos = d.treinos || [];
  const vazia = !_temTreinoReal(treinos);
  const semanaAtual = iso(getMonday(new Date())) === iso(monday);
  // Painel de geração: só na semana vigente e vazia.
  const panel = document.getElementById('novatoPanel');
  if (panel) panel.style.display = (vazia && semanaAtual) ? '' : 'none';
  if (vazia && semanaAtual) {
    const titulo = document.getElementById('npTitulo');
    const sub = document.getElementById('npSub');
    if (d.tem_historico) {
      if (titulo) titulo.textContent = 'Você ainda não gerou os treinos desta semana';
      if (sub) sub.textContent = 'Parece que a semana começou sem um plano. Posso montar um baseado no seu histórico recente.';
    } else {
      if (titulo) titulo.textContent = 'Sua semana está vazia';
      if (sub) sub.textContent = 'Você ainda não tem treinos nesta semana. Posso montar um plano pra você a partir do seu perfil (idade, peso, objetivo e dias de treino) — ou você conecta o Garmin para importar seus treinos.';
    }
  }
  // Botão de apagar: só para semana gerada automaticamente e ainda não realizada.
  const btnApagar = document.getElementById('btnApagarGerados');
  if (btnApagar) {
    const geradaAuto = d.origem === 'auto' && !treinos.some(t => t.resultado);
    btnApagar.style.display = (geradaAuto && !vazia) ? '' : 'none';
  }
}

async function gerarPrimeiraSemana() {
  const panel = document.getElementById('novatoPanel');
  const originalHTML = panel.innerHTML;
  panel.innerHTML = `<div class="bike-loading">
    <svg width="100" height="72" viewBox="0 0 100 72" fill="none" xmlns="http://www.w3.org/2000/svg">
      <g class="wheel-r">
        <circle cx="26" cy="54" r="16" stroke="#2e7d32" stroke-width="3" fill="none"/>
        <line x1="26" y1="38" x2="26" y2="70" stroke="#2e7d32" stroke-width="1.5"/>
        <line x1="10" y1="54" x2="42" y2="54" stroke="#2e7d32" stroke-width="1.5"/>
        <line x1="14.7" y1="43.7" x2="37.3" y2="64.3" stroke="#2e7d32" stroke-width="1.5"/>
        <line x1="37.3" y1="43.7" x2="14.7" y2="64.3" stroke="#2e7d32" stroke-width="1.5"/>
      </g>
      <g class="wheel-f">
        <circle cx="74" cy="54" r="16" stroke="#2e7d32" stroke-width="3" fill="none"/>
        <line x1="74" y1="38" x2="74" y2="70" stroke="#2e7d32" stroke-width="1.5"/>
        <line x1="58" y1="54" x2="90" y2="54" stroke="#2e7d32" stroke-width="1.5"/>
        <line x1="62.7" y1="43.7" x2="85.3" y2="64.3" stroke="#2e7d32" stroke-width="1.5"/>
        <line x1="85.3" y1="43.7" x2="62.7" y2="64.3" stroke="#2e7d32" stroke-width="1.5"/>
      </g>
      <!-- frame -->
      <line x1="26" y1="54" x2="50" y2="20" stroke="#1b5e20" stroke-width="2.5" stroke-linecap="round"/>
      <line x1="50" y1="20" x2="74" y2="54" stroke="#1b5e20" stroke-width="2.5" stroke-linecap="round"/>
      <line x1="50" y1="20" x2="38" y2="54" stroke="#1b5e20" stroke-width="2.5" stroke-linecap="round"/>
      <line x1="50" y1="20" x2="56" y2="10" stroke="#1b5e20" stroke-width="2.5" stroke-linecap="round"/>
      <line x1="52" y1="10" x2="62" y2="10" stroke="#1b5e20" stroke-width="3" stroke-linecap="round"/>
      <circle cx="50" cy="54" r="4" fill="#2e7d32"/>
    </svg>
    <div class="np-titulo">Montando sua semana...</div>
    <div class="np-sub">A IA está analisando seu histórico e criando um plano personalizado.</div>
    <div class="bike-progress-wrap"><div class="bike-progress-bar" id="bikeProgressBar"></div></div>
    <div class="bike-progress-pct" id="bikeProgressPct">0%</div>
  </div>`;

  let pct = 0;
  const bar = document.getElementById('bikeProgressBar');
  const lbl = document.getElementById('bikeProgressPct');
  const timer = setInterval(() => {
    const step = pct < 40 ? 3 : pct < 70 ? 1.5 : pct < 88 ? 0.5 : 0.1;
    pct = Math.min(pct + step, 89);
    if (bar) bar.style.width = pct + '%';
    if (lbl) lbl.textContent = Math.round(pct) + '%';
  }, 400);

  try {
    const r = await fetch(`/workout/gerar-primeira-semana/${iso(monday)}`, {method: 'POST'});
    clearInterval(timer);
    if (!r.ok) throw new Error(await r.text());
    if (bar) bar.style.width = '100%';
    if (lbl) lbl.textContent = '100%';
    await new Promise(res => setTimeout(res, 400));
    panel.innerHTML = originalHTML;
    toast('✅ Semana montada! Bons treinos.', 'ok');
    await load();
  } catch(e) {
    clearInterval(timer);
    panel.innerHTML = originalHTML;
    toast('Erro ao montar a semana: ' + e.message, 'err');
  }
}

async function apagarTreinosGerados() {
  if (!confirm('Apagar todos os treinos gerados automaticamente nesta semana?')) return;
  const btn = document.getElementById('btnApagarGerados');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Apagando...';
  try {
    const r = await fetch(`/workout/primeira-semana/${iso(monday)}`, {method: 'DELETE'});
    if (!r.ok) throw new Error(await r.text());
    toast('🗑 Treinos gerados apagados.', 'ok');
    await load();
  } catch(e) {
    toast('Erro ao apagar: ' + e.message, 'err');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '🗑 Apagar treinos gerados';
  }
}

// Motivo pelo qual "Gerar próxima semana" está travado — null = liberado.
// Guardado fora da função porque o clique precisa explicar o bloqueio.
let _motivoBloqueioGen = null;

// Um treino conta como concluído quando tem resultado (bike — vem do Garmin/
// Strava) ou execução registrada. Academia NUNCA gera atividade de ciclismo no
// Garmin: se fosse cobrada por `resultado`, um dia de academia travaria a
// geração da próxima semana para sempre.
function _treinoConcluido(t) {
  if (t.resultado) return true;
  const exec = t.execucao || (t.academia || {}).execucao || null;
  return !!(exec && (exec.itens_feitos || []).length);
}

function _atualizarBotaoProximaSemana(treinos, proximaGerada) {
  const btn = document.getElementById('btnGenSemana');
  if (!btn) return;
  const hojeISO = localIso(new Date());
  const semanaAtual = iso(getMonday(new Date())) === iso(monday);

  // Só dias de HOJE em diante travam. Dia que já passou sem resultado é treino
  // perdido: vira dado para a IA analisar, não pode bloquear a semana seguinte
  // para sempre (era o que acontecia — bastava furar um treino na terça e o
  // botão nunca mais habilitava).
  const pendentes = (treinos || []).filter(t =>
    t.tipo !== 'DESCANSO' && t.origem !== 'extra'
    && t.data >= hojeISO && !_treinoConcluido(t)
  );

  const ativos = (treinos || []).filter(t => t.tipo !== 'DESCANSO' && t.origem !== 'extra');

  if (!semanaAtual) {
    _motivoBloqueioGen = 'A próxima semana só é gerada a partir da semana atual — clique em "Hoje" primeiro.';
  } else if (!ativos.length) {
    _motivoBloqueioGen = 'Esta semana está vazia — a IA precisa dela para planejar a próxima.';
  } else if (proximaGerada) {
    _motivoBloqueioGen = 'A próxima semana já foi gerada — use a seta ▶ para abri-la.';
  } else if (pendentes.length) {
    const dias = pendentes.map(t => {
      const d = new Date(t.data + 'T12:00:00');
      return `${DIAS_PT[d.getDay()]} ${t.data.slice(8)}/${t.data.slice(5, 7)}`;
    }).join(', ');
    _motivoBloqueioGen = `Faltam treinos desta semana: ${dias}. Conclua (ou sincronize com o Garmin) para gerar a próxima.`;
  } else {
    _motivoBloqueioGen = null;
  }

  const habilitado = !_motivoBloqueioGen;
  // De propósito NÃO usa `disabled`: no celular não existe tooltip, então um
  // botão travado que não faz nada ao ser tocado não explica o motivo. Ele fica
  // esmaecido e o clique responde com o motivo exato.
  btn.disabled = false;
  btn.title = _motivoBloqueioGen || '';
  btn.style.opacity = habilitado ? '1' : '0.5';
  btn.style.cursor = 'pointer';
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

async function sincronizarGarmin() {
  const btn = document.getElementById('btnGarmin');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner" style="border-color:rgba(0,0,0,.2);border-top-color:#333"></span> Enviando e sincronizando...';
  try {
    // 0. Salva o estado atual da semana ANTES de mexer no Garmin. Sem isto, o
    //    envio lê o estado antigo do banco e re-cria no Garmin o treino que você
    //    acabou de excluir/mover — e o pull seguinte o traz "de volta".
    const rSave = await fetch('/workout/semana', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        semana_inicio: iso(monday),
        objetivo: document.getElementById('objetivo').value.trim(),
        treinos: collect(),
      }),
    });
    if (!rSave.ok) throw new Error(await rSave.text());

    // 1. Envia treinos da semana pro Garmin (push).
    //    O push NÃO pode abortar o pull: se o envio falha (treino já existe lá,
    //    sessão expirada, indisponibilidade do Garmin), a importação da
    //    atividade já realizada ficava sem rodar e o treino do dia aparecia
    //    "sem atividade anexada" mesmo estando no Garmin Connect.
    let enviados = null;
    let erroEnvio = null;
    try {
      const rEnv = await fetch(`/workout/reenviar-garmin/${iso(monday)}`, {method: 'POST'});
      if (!rEnv.ok) throw new Error(await rEnv.text());
      enviados = (await rEnv.json()).enviados;
    } catch(e) {
      erroEnvio = e.message;
    }

    // 2. Sincroniza atividades e treinos planejados do Garmin (pull)
    const rSync = await fetch(`/workout/garmin/sync/${iso(monday)}`, {method: 'POST'});
    if (!rSync.ok) throw new Error(await rSync.text());
    const dSync = await rSync.json();

    const envMsg = erroEnvio ? 'envio falhou' : `${enviados} enviado(s)`;
    const msg = `${erroEnvio ? '⚠️' : '✅'} ${envMsg} · ${dSync.atividades_processadas} atividade(s) importada(s)`;
    toast(msg, erroEnvio ? 'err' : 'ok');
    if (erroEnvio) console.warn('Garmin push falhou:', erroEnvio);
    await load();
  } catch(e) {
    toast('❌ Garmin: ' + e.message, 'err');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '📡 Enviar + Sincronizar Garmin';
  }
}

function fecharGenModal(e) {
  document.getElementById('genModal').classList.remove('show');
}

const TIPO_CORES = {
  Z2_LONGO:'#1565c0', TIROS:'#c62828', VO2MAX:'#6a1b9a',
  TEMPO:'#e65100', FORCA:'#5d4037', ACADEMIA:'#2e7d32', RECUPERACAO:'#00695c', DESCANSO:'#607d8b',
  TESTE_FTP:'#7c3aed',
};
const TIPO_LABELS2 = {
  Z2_LONGO:'Z2 Longo', TIROS:'Tiros', VO2MAX:'VO2Max',
  TEMPO:'Tempo', FORCA:'Força Bike', ACADEMIA:'Academia', RECUPERACAO:'Recuperação', DESCANSO:'Descanso',
  TESTE_FTP:'Teste FTP',
};
const DIAS_PT = ['Dom','Seg','Ter','Qua','Qui','Sex','Sáb'];

let _genData = null;

async function gerarProximaSemana() {
  if (_motivoBloqueioGen) { toast(_motivoBloqueioGen, 'err'); return; }
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
      const acSub2 = t.academia;
      const acHTML2 = acSub2 && acSub2.descricao ? renderAcademiaBloco(acSub2) : '';
      return `<div class="gen-modal-treino">
        <div class="gmt-head">
          <span class="gmt-data">${DIAS_PT[dia.getDay()]} ${t.data.slice(5)}</span>
          <span class="gmt-tipo" style="background:${TIPO_CORES[t.tipo]||'#607d8b'}">${TIPO_LABELS2[t.tipo]||t.tipo}</span>
          ${durStr ? `<span class="gmt-dur">⏱ ${durStr}</span>` : ''}
        </div>
        ${t.descricao ? `<div class="gmt-desc">${t.descricao}</div>` : ''}
        ${acHTML2}
      </div>`;
    }).join('');

    head.innerHTML = `<h3>🤖 Próxima semana</h3><div class="modal-sub">${d.semana_proxima}</div>`;
    const geminiAviso = d.modelo_usado === 'gemini'
      ? `<div id="geminiAviso" style="background:#fff3e0;border:1.5px solid #ff9800;border-radius:8px;padding:10px 14px;margin-bottom:12px;font-size:.85rem;color:#e65100;display:flex;align-items:center;gap:8px">
          <span>⚠️</span>
          <span>Cota do Claude esgotada — plano gerado pelo <strong>Gemini</strong> (modo gratuito). Qualidade pode ser ligeiramente menor.</span>
          <button onclick="document.getElementById('geminiAviso').remove()" style="margin-left:auto;background:none;border:none;cursor:pointer;font-size:1rem;color:#e65100">✕</button>
        </div>`
      : '';
    body.innerHTML = `
      ${geminiAviso}
      ${d.analise_semana ? `<div class="gen-analise">📊 ${d.analise_semana}</div>` : ''}
      ${d.progressao ? `<div class="gen-prog">⬆️ ${d.progressao}</div>` : ''}
      ${cards}
      <button class="btn-enviar" id="btnEnviarGarmin" onclick="enviarParaGarmin()">
        📡 Salvar + Enviar pro Garmin
      </button>`;
    if (d.modelo_usado === 'gemini') setTimeout(() => { const el = document.getElementById('geminiAviso'); if (el) el.remove(); }, 30000);
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
    academia:     t.academia     || null,
    periodo:      t.periodo      || null,
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
    // navega para a semana recém-gerada e recarrega a grade com os treinos novos
    monday = new Date(_genData.semana_proxima + 'T12:00:00');
    await load();
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

  // Próximas provas em lista compacta: dar o mesmo destaque a uma prova daqui
  // 25 dias e a outra daqui 4 meses esconderia a que exige ação agora.
  const seguintes = d.seguintes || [];
  const seguintesHTML = seguintes.length ? `
    <div class="pp-seguintes">
      <div class="pf-titulo">Depois dessa (${seguintes.length})</div>
      ${seguintes.map(s => {
        const [, sm, sd] = (s.data || '').split('-');
        const sDataFmt = sd ? (sd + '/' + sm) : (s.data || '');
        const dias = s.dias_restantes;
        const quando = dias <= 0 ? 'hoje' : (dias === 1 ? '1 dia' : dias + ' dias');
        const det = [];
        if (s.local) det.push(esc(s.local));
        if (s.distancia_km) det.push(s.distancia_km + ' km');
        return `<div class="ps-linha">
          <span class="ps-data">${sDataFmt}</span>
          <span class="ps-nome">${esc(s.nome)}${det.length ? ` <small>${det.join(' · ')}</small>` : ''}</span>
          <span class="ps-dias">${quando}</span>
          <span class="ps-fase">${esc(s.fase_label || '')}</span>
        </div>`;
      }).join('')}
    </div>` : '';

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
    ${seguintesHTML}
    <div style="margin-top:10px"><a class="pp-link" href="/workout/calendario">Gerenciar provas →</a></div>
  </div>`;
}

function renderFTPBtn() {
  const area = document.getElementById('ftpBtnArea');
  if (!area) return;
  const dias = window.DIAS_FTP;
  if (window.FTP_ON && (dias === null || dias >= 90)) {
    area.innerHTML = '<button class="btn btn-ftp" id="btnCriarFTP" onclick="abrirModalFTP()">⚡ Criar Teste FTP</button>';
  } else if (window.FTP_ON && dias !== null && dias < 90) {
    const falta = 90 - Math.max(dias, 0);
    area.innerHTML = `<div id="ftpCountdown" style="font-size:.8rem;color:#7c3aed;font-weight:600;padding:8px 12px;background:#f3e8ff;border-radius:8px;text-align:center">⚡ Próximo Teste FTP em <strong>${falta} dia${falta !== 1 ? 's' : ''}</strong></div>`;
    setTimeout(() => { const el = document.getElementById('ftpCountdown'); if (el) el.remove(); }, 30 * 1000);
  }
}

load();
carregarProva();
renderFTPBtn();
window.addEventListener('mtb:recarregar', load);

function toggleTema() {
  const cur = document.documentElement.getAttribute('data-theme') || 'light';
  _aplicarTema(cur === 'dark' ? 'light' : 'dark');
}
function _aplicarTema(t) {
  localStorage.setItem('mtb-tema', t);
  document.documentElement.setAttribute('data-theme', t);
  const btn = document.getElementById('themeBtn');
  if (btn) btn.textContent = t === 'dark' ? '☀️' : '🌙';
  fetch('/workout/tema', {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({tema:t})});
}
// Sincroniza ícone do botão com o tema carregado antes do DOMContentLoaded
(function(){
  const t = localStorage.getItem('mtb-tema') || 'light';
  const btn = document.getElementById('themeBtn');
  if (btn) btn.textContent = t === 'dark' ? '☀️' : '🌙';
})();
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

    # Rótulos curtos: são 5 links de nutrição e, somados a Evolução, Provas,
    # Perfil, Garmin, nome, admin e assinatura, o header passava de 12 itens.
    nav_nutri = (
        '<a href="/nutrition/guia">🥗 Nutrição</a>\n'
        '    <a href="/nutrition/alimentos">🍽️ Alimentos</a>\n'
        '    <a href="/nutrition/chat">💬 Cardápio</a>\n'
        '    <a href="/nutrition/ajuste">🍔 Fuga</a>\n'
        '    <a href="/nutrition/config" class="nav-icone" title="Horários das refeições">⏰</a>'
    ) if perder_peso else ""

    # Só o primeiro nome, e sem o 👤 — que já é o ícone do link "Perfil" ao
    # lado. O nome inteiro é o item mais largo da barra e informa o mesmo.
    primeiro_nome = (nome or "").split(" ")[0]
    nav_user = f'<span class="nav-user" title="{nome}">{primeiro_nome}</span>' if primeiro_nome else ""

    nutricao_on_js = "true" if perder_peso else "false"

    garmin_conectado = bool(((u.get("integracao") or {}).get("garmin") or {}).get("email"))
    # Conectado é status, não ação: vira ícone com tooltip. Desconectado
    # continua com texto — aí é uma pendência que o atleta precisa resolver.
    garmin_nav = (
        '<a href="/workout/integracao" class="nav-icone" title="Garmin conectado — ver integração">⌚</a>'
        if garmin_conectado else
        '<a href="/workout/integracao">⌚ Conectar Garmin</a>'
    )
    garmin_btn = (
        '<a class="btn btn-sec" href="/workout/integracao">✅ Garmin conectado</a>'
        if garmin_conectado else
        '<a class="btn btn-sec" href="/workout/integracao">⌚ Conectar Garmin</a>'
    )

    from app.services.config_service import get_ftp, get_zonas_potencia as _get_zp, get_zonas as _get_zonas_fc
    from app.services.user_service import get_por_id
    from datetime import date as _date, datetime as _datetime
    import pytz as _pytz
    import json as _json
    ftp_val, _ = await get_ftp(request.state.user_id)
    ftp_on_js = "true" if ftp_val else "false"
    zonas_pot = await _get_zp(request.state.user_id)
    zonas_pot_js = _json.dumps(zonas_pot or {})
    zonas_fc = await _get_zonas_fc(request.state.user_id)
    zonas_fc_js = _json.dumps(zonas_fc or {})
    garmin_on_js = "true" if garmin_conectado else "false"

    _user = await get_por_id(request.state.user_id) or {}
    _ftp_agendado = _user.get("ultimo_ftp_agendado")
    if _ftp_agendado:
        try:
            _hoje_br = _datetime.now(_pytz.timezone("America/Sao_Paulo")).date()
            _dias_ftp = (_hoje_br - _date.fromisoformat(_ftp_agendado)).days
        except ValueError:
            _dias_ftp = None
    else:
        _dias_ftp = None
    dias_ftp_js = str(_dias_ftp) if _dias_ftp is not None else "null"

    tema = (u.get("preferencias") or {}).get("tema") or "light"
    return (
        HTML
        .replace("{{NAV_NUTRI}}", nav_nutri)
        .replace("{{NAV_USER}}", nav_user)
        .replace("{{NUTRICAO_ON}}", nutricao_on_js)
        .replace("{{GARMIN_NAV}}", garmin_nav)
        .replace("{{GARMIN_BTN}}", garmin_btn)
        .replace("{{FTP_ON}}", ftp_on_js)
        .replace("{{GARMIN_ON}}", garmin_on_js)
        .replace("{{DIAS_FTP}}", dias_ftp_js)
        .replace("{{ZONAS_POT}}", zonas_pot_js)
        .replace("{{ZONAS_FC}}", zonas_fc_js)
        .replace("__TEMA__", tema)
    )
