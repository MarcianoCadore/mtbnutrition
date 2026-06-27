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
    nav > div:first-of-type { flex-shrink: 0; }
    nav .nav-links { margin-left: auto; display: flex; gap: 16px; align-items: center; }
    nav .nav-links a { color: #fff; text-decoration: none; font-size: 0.88rem; opacity: .85; white-space: nowrap; }
    nav .nav-links a:hover { opacity: 1; text-decoration: underline; }
    nav .nav-toggle { display: none; margin-left: auto; background: rgba(255,255,255,.15); border: none; color: #fff; font-size: 1.4rem; line-height: 1; width: 42px; height: 42px; border-radius: 8px; cursor: pointer; }
    nav .nav-user { color: rgba(255,255,255,.75); font-size: 0.85rem; font-weight: 600; white-space: nowrap; }
    .admin-nav-link { color:#fff; text-decoration:none; font-size:.8rem; font-weight:700; background:rgba(255,255,255,.22); padding:4px 13px; border-radius:20px; white-space:nowrap; }

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
    .indoor-area { margin-top: 8px; border-top: 1px dashed var(--border); padding-top: 8px; }
    .indoor-toggle { display: flex; gap: 4px; border-radius: 8px; overflow: hidden; border: 1.5px solid var(--border); }
    .indoor-toggle button { flex: 1; padding: 7px 4px; border: none; font-size: .78rem; font-weight: 700; cursor: pointer; background: #f3f4f6; color: var(--muted); transition: .15s; }
    .indoor-toggle button.ativo { background: var(--green); color: #fff; }
    .indoor-toggle button:disabled { opacity: .5; cursor: not-allowed; }
    .indoor-sync-msg { font-size: .72rem; margin-top: 4px; text-align: center; min-height: 14px; color: var(--muted); }
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
    .tipo-ACADEMIA    { background: #2e7d32; }
    .tipo-RECUPERACAO { background: #00695c; }
    .tipo-DESCANSO    { background: #607d8b; }
    .tipo-TESTE_FTP   { background: #7c3aed; }
    .academia-bloco { background: #e8f5e9; border-radius: 8px; padding: 10px 12px; margin-top: 8px; border-left: 3px solid #2e7d32; }
    .academia-bloco .ac-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
    .academia-bloco .ac-titulo { font-size: .72rem; font-weight: 700; color: #2e7d32; }
    .academia-bloco .ac-dur { font-size: .7rem; color: #555; }
    .academia-bloco .ac-foco { font-size: .7rem; color: #388e3c; font-style: italic; margin-bottom: 6px; }
    .academia-bloco .ac-porque { font-size: .75rem; color: #444; line-height: 1.4; margin-bottom: 6px; background: #fff; border-radius: 4px; padding: 5px 8px; }
    .academia-bloco .ac-exercicios { list-style: none; padding: 0; margin: 0 0 6px 0; }
    .academia-bloco .ac-exercicios li { font-size: .75rem; color: var(--text); line-height: 1.5; padding: 2px 0; border-bottom: 1px solid #c8e6c9; }
    .academia-bloco .ac-exercicios li:last-child { border-bottom: none; }
    .academia-bloco .ac-obs { font-size: .72rem; color: #666; line-height: 1.4; }

    .actions { display: flex; gap: 12px; flex-wrap: wrap; }
    .btn { padding: 13px 22px; border: none; border-radius: 10px; font-size: .95rem; font-weight: 700; cursor: pointer; transition: all .2s; display: flex; align-items: center; gap: 6px; }
    .btn-save  { background: var(--green);  color: #fff; flex: 1; justify-content: center; }
    .btn-save:hover:not(:disabled)  { background: #0e7166; }
    .btn-test  { background: var(--green2); color: #fff; }
    .btn-test:hover:not(:disabled)  { background: #1da851; }
    .btn-sec   { background: #fff; color: var(--text); border: 1.5px solid var(--border); }
    .btn-sec:hover:not(:disabled)   { border-color: var(--green); color: var(--green); }
    .btn-ftp   { background: #7c3aed; color: #fff; }
    .btn-ftp:hover:not(:disabled)   { background: #6d28d9; }
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

  <div id="provaPanel"></div>

  <div class="card">
    <div class="section-label">💡 Objetivo / Foco da Semana</div>
    <textarea id="objetivo" placeholder="Ex: Semana de base aeróbica com 2 sessões de Z2 longo. Foco em manter FC abaixo de 153 bpm. Volume total: ~12h de pedal..."></textarea>
  </div>

  <div class="section-label" style="margin-bottom:12px">📅 Treinos da Semana</div>
  <div class="novato-panel" id="novatoPanel" style="display:none">
    <div class="np-emoji">🚴</div>
    <div class="np-titulo">Sua semana está vazia</div>
    <div class="np-sub">Você ainda não tem treinos nesta semana. Posso montar um plano pra você
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

function _rangeZona(n) {
  const zp = window.ZONAS_POT;
  if (!window.FTP_ON || !zp || !zp.zonas) return null;
  const z = zp.zonas.find(zz => zz.zona === n);
  if (!z) return null;
  if (z.min === 0) return `até ${z.max}W`;
  if (z.max >= 9999) return `>${z.min}W`;
  return `${z.min}–${z.max}W`;
}

function _estruturaIndoor(tipo) {
  const z1 = _rangeZona(1), z2 = _rangeZona(2), z3 = _rangeZona(3), z5 = _rangeZona(5);
  if (!z1) return null;
  switch (tipo) {
    case 'Z2_LONGO':
      return [
        `Aquecimento 15 min em Z1 (${z1})`,
        `Bloco principal contínuo em Z2 (${z2})`,
        `Volta à calma 15 min em Z1 (${z1})`,
      ];
    case 'TEMPO':
      return [
        `Aquecimento 15 min em Z2 (${z2})`,
        `3× [10 min em Z3 (${z3}) + 5 min Z2]`,
        `Volta à calma 10 min em Z2 (${z2})`,
      ];
    case 'FORCA':
      return [
        `Aquecimento 15 min em Z2 (${z2})`,
        `4× [6 min em Z3 (${z3}) com cadência 50–60 rpm + 4 min Z2]`,
        `Volta à calma 10 min em Z2 (${z2})`,
      ];
    case 'TIROS':
      return [
        `Aquecimento 15 min em Z2 (${z2})`,
        `8× [30 s máximo em Z5 (${z5}) + 3,5 min Z1]`,
        `Volta à calma 15 min em Z2 (${z2})`,
      ];
    case 'VO2MAX':
      return [
        `Aquecimento 15 min em Z2 (${z2})`,
        `4× [4 min forte em Z5 (${z5}) + 4 min Z2]`,
        `Volta à calma 15 min em Z2 (${z2})`,
      ];
    case 'RECUPERACAO':
      return [`Pedal leve e contínuo em Z1 (${z1})`];
    case 'TESTE_FTP':
      return [
        `Aquecimento 10 min em Z1 (${z1})`,
        `Progressivo 5 min em Z3 (${z3})`,
        '3× [30s máximo Z5 + 1 min Z1 recuperação]',
        'Pré-teste 2 min suave Z1',
        'TESTE 20 min — potência máxima sustentável (Z4)',
        'Desaquecimento 15 min em Z1',
      ];
    default:
      return null;
  }
}

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
    obj: 'Força específica na bike. Recruta mais fibras musculares pedalando com cadência baixa e marcha pesada.',
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
  TESTE_FTP: {
    obj: 'Teste de FTP (Functional Threshold Power). Mede a potência máxima que você sustenta por ~1h. Resultado × 0,95 = novo FTP.',
    estrutura: [
      'Aquecimento 10 min em Z1 (abaixo de 139 bpm)',
      'Progressivo 5 min em Z3 (148–155 bpm)',
      '3× [30s máximo Z5 + 1 min Z1 recuperação]',
      'Pré-teste 2 min suave Z1',
      'TESTE 20 min — potência máxima sustentável (Z4)',
      'Desaquecimento 15 min em Z1',
    ],
    dica: 'Saída CONTROLADA nos primeiros 3 min. Aumente gradualmente. Pedal leve em Z1 durante os 3 min de desaquecimento ao final.',
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

function renderAcademiaBloco(ac) {
  const ad = ac.duracao_min || 0;
  const adStr = ad ? ((Math.floor(ad/60)>0?Math.floor(ad/60)+'h':'')+(ad%60>0?ad%60+'min':'')) : '';
  const raw = (ac.descricao || '').replace(/</g, '&lt;');
  const lines = raw.split('\\n');

  const focoM = lines[0] ? lines[0].match(/\(foco:\s*([^)]+)\)/i) : null;
  const foco = focoM ? focoM[1] : '';

  let porqueText = '', obsText = '', section = '';
  const exItems = [];

  for (let i = 1; i < lines.length; i++) {
    const l = lines[i].trim();
    if (!l) continue;
    if (l.indexOf('POR QUE HOJE:') === 0) { section = 'porque'; porqueText = l.slice(13).trim(); continue; }
    if (l.indexOf('EXERC') === 0 && l.indexOf(':') > 0) { section = 'ex'; continue; }
    if (l.indexOf('OBSERVA') === 0 && l.indexOf(':') > 0) { section = 'obs'; continue; }
    if (section === 'porque') porqueText += ' ' + l;
    else if (section === 'ex') exItems.push(l);
    else if (section === 'obs') obsText += (obsText ? ' · ' : '') + l.replace(/^-\s*/, '');
  }

  let html = '<div class="academia-bloco">';
  html += '<div class="ac-header"><span class="ac-titulo">🏋️ Academia</span>';
  if (adStr) html += '<span class="ac-dur">&#8987; ' + adStr + '</span>';
  html += '</div>';
  if (foco)       html += '<div class="ac-foco">Foco: ' + foco + '</div>';
  if (porqueText) html += '<div class="ac-porque">' + porqueText + '</div>';
  if (exItems.length) {
    html += '<ul class="ac-exercicios">';
    for (let i = 0; i < exItems.length; i++) html += '<li>' + exItems[i] + '</li>';
    html += '</ul>';
  }
  if (obsText) html += '<div class="ac-obs">&#128204; ' + obsText + '</div>';
  html += '</div>';
  return html;
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

    _planejado[key] = {tipo: t.tipo, duracao_min: t.duracao_min, cadencia_rpm: t.cadencia_rpm, descricao: t.descricao, academia: t.academia || null, indoor: t.indoor || false};
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

    const isAcademia = t.tipo === 'ACADEMIA';
    const cadReal    = (res && res.cadencia_media_rpm) ? res.cadencia_media_rpm : '';
    const avgPowReal = (res && res.avg_power) ? res.avg_power : null;
    const metricsHTML = (dur || dist || elev || cadReal || avgPowReal)
      ? `<div class="metrics" id="metrics-${key}">
           ${dur  ? `<div class="metric"><div class="mv">${dur} min</div><div class="ml">Duração</div></div>` : ''}
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
      </ul>` : '';

    const acSub = t.academia;
    const academiaSubHTML = acSub && acSub.descricao ? renderAcademiaBloco(acSub) : '';

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
              <label>${isAcademia ? 'Exercícios' : 'Notas'}</label>
              <button class="info-treino" onclick="abrirTreinoInfo('${key}')" title="Ver especificação do treino"><span class="ic">ⓘ</span> saber mais</button>
            </div>
            <textarea id="desc-${key}" placeholder="${isAcademia ? 'Lista de exercícios...' : 'Detalhes...'}" ${lockAttr}>${desc}</textarea>
          </div>
          ${academiaSubHTML}
        </div>

        <div id="rest-${key}" style="${hide ? '' : 'display:none'}">
          <div class="rest-badge"><span class="icon">😴</span>Dia de descanso</div>
        </div>
        ${!isFuturo ? `<button class="rest-toggle" id="resttoggle-${key}" onclick="toggleRest('${key}')">
          ${hide ? '🏃 Adicionar treino' : '🛌 Marcar descanso'}
        </button>` : ''}

        ${window.FTP_ON && !hide ? `<div class="indoor-area">
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
  if (res.avg_hr) mItems.push(`<div class="metric"><div class="mv">${res.avg_hr} bpm</div><div class="ml">FC média</div></div>`);
  if (res.max_hr) mItems.push(`<div class="metric"><div class="mv">${res.max_hr} bpm</div><div class="ml">FC máx</div></div>`);
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
  const acSub = p.academia;

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
    // Treino de bike: mostra estrutura normal
    if (esp) {
      const isIndoor = p.indoor || false;
      const estrutura = (isIndoor && _estruturaIndoor(tipo)) || esp.estrutura;
      const modoLabel = isIndoor ? ' <span style="font-size:.72rem;background:#e3f2fd;color:#1565c0;border-radius:4px;padding:1px 6px;font-weight:700;vertical-align:middle">🏠 Indoor — Watts</span>' : '';
      corpo += `<div class="esp-obj">${esp.obj}</div>`;
      corpo += `<div class="esp-bloco"><div class="esp-titulo">Como executar${modoLabel}</div>`
             + `<ul class="esp-lista">${estrutura.map(s => `<li>${s}</li>`).join('')}</ul></div>`;
      corpo += `<div class="esp-dica">💡 ${esp.dica}</div>`;
    }
    if (notas && notas.trim()) {
      corpo += `<div class="esp-bloco" style="margin-top:14px"><div class="esp-titulo">Notas do treino</div>`
             + `<div class="esp-notas">${notas.replace(/</g,'&lt;').replace(/\\n/g,'<br>')}</div></div>`;
    }
    // Sub-objeto academia (bike + gym no mesmo dia): seção separada
    if (acSub && acSub.descricao) {
      const adStr = acSub.duracao_min ? ((Math.floor(acSub.duracao_min/60)>0?Math.floor(acSub.duracao_min/60)+'h':'')+(acSub.duracao_min%60>0?acSub.duracao_min%60+'min':'')) : '';
      corpo += `<div class="esp-bloco" style="margin-top:18px;border-top:1.5px solid #c8e6c9;padding-top:14px">`
             + `<div class="esp-titulo" style="color:#2e7d32">🏋️ Academia${adStr?' · ⏱ '+adStr:''}</div>`
             + `<div class="esp-notas" style="background:#e8f5e9">${acSub.descricao.replace(/</g,'&lt;').replace(/\\n/g,'<br>')}</div></div>`;
    }
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
  try {
    const r = await fetch(`/workout/semana/${iso(monday)}`);
    const d = await r.json();
    document.getElementById('objetivo').value = d.objetivo || '';
    buildCards(d.treinos || []);
    _atualizarBotaoProximaSemana(d.treinos || []);
    _atualizarBotoesNovato(d);
  } catch {
    buildCards([]);
    _atualizarBotaoProximaSemana([]);
    _atualizarBotoesNovato({treinos: []});
  }
}

function _temTreinoReal(treinos) {
  return (treinos || []).some(t => t.tipo !== 'DESCANSO' && t.duracao_min);
}

function _atualizarBotoesNovato(d) {
  const treinos = d.treinos || [];
  const vazia = !_temTreinoReal(treinos);
  // Painel de boas-vindas (gerar / conectar Garmin): só quando a semana está vazia.
  const panel = document.getElementById('novatoPanel');
  if (panel) panel.style.display = vazia ? '' : 'none';
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

function _atualizarBotaoProximaSemana(treinos) {
  const btn = document.getElementById('btnGenSemana');
  if (!btn) return;
  const semanaAtual = iso(getMonday(new Date())) === iso(monday);
  const treinosAtivos = treinos.filter(t => t.tipo !== 'DESCANSO');
  const todosConcluidos = treinosAtivos.length > 0 && treinosAtivos.every(t => !!t.resultado);
  const habilitado = semanaAtual && todosConcluidos;
  btn.disabled = !habilitado;
  btn.title = habilitado ? '' : 'Conclua todos os treinos da semana para gerar a próxima semana';
  btn.style.opacity = habilitado ? '1' : '0.5';
  btn.style.cursor = habilitado ? 'pointer' : 'not-allowed';
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
      if (d.avg_power)    items.push(`<div class="metric"><div class="mv">${d.avg_power}W</div><div class="ml">Potência média</div></div>`);
      if (d.norm_power)   items.push(`<div class="metric"><div class="mv">${d.norm_power}W</div><div class="ml">NP</div></div>`);
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
        TEMPO: 'Tempo', FORCA: 'Força Bike', ACADEMIA: 'Academia', RECUPERACAO: 'Recuperação', DESCANSO: 'Descanso',
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
  btn.innerHTML = '<span class="spinner" style="border-color:rgba(0,0,0,.2);border-top-color:#333"></span> Enviando e sincronizando...';
  try {
    // 1. Envia treinos da semana pro Garmin (push)
    const rEnv = await fetch(`/workout/reenviar-garmin/${iso(monday)}`, {method: 'POST'});
    if (!rEnv.ok) throw new Error(await rEnv.text());
    const dEnv = await rEnv.json();

    // 2. Sincroniza atividades e treinos planejados do Garmin (pull)
    const rSync = await fetch(`/workout/garmin/sync/${iso(monday)}`, {method: 'POST'});
    if (!rSync.ok) throw new Error(await rSync.text());
    const dSync = await rSync.json();

    const msg = `✅ ${dEnv.enviados} enviado(s) · ${dSync.atividades_processadas} atividade(s) importada(s)`;
    toast(msg, 'ok');
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

    garmin_conectado = bool(((u.get("integracao") or {}).get("garmin") or {}).get("email"))
    garmin_nav = (
        '<a href="/workout/integracao">✅ Garmin conectado</a>'
        if garmin_conectado else
        '<a href="/workout/integracao">⌚ Conectar Garmin</a>'
    )
    garmin_btn = (
        '<a class="btn btn-sec" href="/workout/integracao">✅ Garmin conectado</a>'
        if garmin_conectado else
        '<a class="btn btn-sec" href="/workout/integracao">⌚ Conectar Garmin</a>'
    )

    from app.services.config_service import get_ftp, get_zonas_potencia as _get_zp
    from app.services.user_service import get_por_id
    from datetime import date as _date, datetime as _datetime
    import pytz as _pytz
    import json as _json
    ftp_val, _ = await get_ftp(request.state.user_id)
    ftp_on_js = "true" if ftp_val else "false"
    zonas_pot = await _get_zp(request.state.user_id)
    zonas_pot_js = _json.dumps(zonas_pot or {})
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
    )
