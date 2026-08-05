"""Landing page pública do MTB Nutrition.

Servida em `/` para visitantes não autenticados (usuários logados são
redirecionados ao portal pelo handler em main.py).
"""

LANDING_HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MTB Nutrition — Treino de ciclismo gerado por IA, no piloto automático</title>
<meta name="description" content="TrainingPeaks e Intervals te dão a planilha; aqui a IA monta a semana inteira, manda pro Garmin ou pro rolo em .zwo, analisa cada pedalada e recalibra a próxima. 14 dias grátis, depois R$ 24,99/mês.">
<meta property="og:title" content="MTB Nutrition — Treino de ciclismo gerado por IA, no piloto automático">
<meta property="og:description" content="As outras plataformas mostram o que você fez. Esta decide o que você faz amanhã: semana montada por IA, no Garmin ou no rolo, com nutrição junto. 14 dias grátis.">
<meta property="og:type" content="website">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Sora:wght@600;700;800&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#07100d;
  --bg2:#0b1712;
  --card:rgba(255,255,255,.035);
  --border:rgba(255,255,255,.09);
  --text:#eaf6f1;
  --muted:#9db8ae;
  --green:#128c7e;
  --green-hi:#2dd4a8;
  --green-glow:rgba(45,212,168,.35);
  --whats:#25d366;
  --radius:18px;
}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{
  font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  background:var(--bg);color:var(--text);line-height:1.6;
  -webkit-font-smoothing:antialiased;overflow-x:hidden;
}
h1,h2,h3{font-family:'Sora','Inter',sans-serif;line-height:1.15;letter-spacing:-.02em}
a{color:inherit;text-decoration:none}
img{max-width:100%}
.wrap{max-width:1120px;margin:0 auto;padding:0 24px}

/* ── Botões ─────────────────────────────────────────── */
.btn{
  display:inline-flex;align-items:center;justify-content:center;gap:8px;
  border-radius:12px;padding:14px 26px;font-size:1rem;font-weight:700;
  font-family:inherit;cursor:pointer;border:none;transition:transform .15s,box-shadow .15s,background .2s;
  white-space:nowrap;
}
.btn-primary{
  background:linear-gradient(135deg,var(--green-hi),var(--green));color:#04211a;
  box-shadow:0 8px 28px -8px var(--green-glow);
}
.btn-primary:hover{transform:translateY(-2px);box-shadow:0 14px 34px -8px var(--green-glow)}
.btn-ghost{background:transparent;color:var(--text);border:1.5px solid var(--border)}
.btn-ghost:hover{border-color:var(--green-hi);color:var(--green-hi)}
.btn-lg{padding:17px 34px;font-size:1.08rem;border-radius:14px}

/* ── Navbar ─────────────────────────────────────────── */
nav{
  position:fixed;top:0;left:0;right:0;z-index:100;
  backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);
  background:rgba(7,16,13,.72);border-bottom:1px solid transparent;
  transition:border-color .3s;
}
nav.scrolled{border-bottom-color:var(--border)}
.nav-inner{max-width:1120px;margin:0 auto;padding:14px 24px;display:flex;align-items:center;gap:28px}
.brand{display:flex;align-items:center;gap:10px;font-family:'Sora',sans-serif;font-weight:800;font-size:1.15rem;white-space:nowrap}
.brand .bike{font-size:1.5rem}
.nav-links{display:flex;gap:26px;flex:1;justify-content:center}
.nav-links a{font-size:.92rem;font-weight:500;color:var(--muted);transition:color .2s}
.nav-links a:hover{color:var(--green-hi)}
.nav-cta{display:flex;gap:10px;align-items:center}
.nav-cta .btn{padding:10px 20px;font-size:.9rem}

/* ── Hero ───────────────────────────────────────────── */
.hero{
  position:relative;padding:150px 0 90px;
  background:
    radial-gradient(900px 480px at 78% -10%,rgba(45,212,168,.14),transparent 62%),
    radial-gradient(700px 420px at 8% 8%,rgba(18,140,126,.18),transparent 60%),
    linear-gradient(180deg,var(--bg2),var(--bg) 75%);
  overflow:hidden;
}
.hero::before{
  content:"";position:absolute;inset:0;pointer-events:none;opacity:.5;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='420' height='420' viewBox='0 0 420 420'%3E%3Cg fill='none' stroke='%232dd4a8' stroke-opacity='.06' stroke-width='1.4'%3E%3Cpath d='M60 340c40-90 90-120 150-120s130 40 150-60'/%3E%3Cpath d='M40 370c50-110 110-150 180-150s150 50 170-80'/%3E%3Cpath d='M20 400c60-130 130-180 210-180s170 60 190-100'/%3E%3C/g%3E%3C/svg%3E");
}
.hero-grid{display:grid;grid-template-columns:1.05fr .95fr;gap:56px;align-items:center;position:relative}
.badge{
  display:inline-flex;align-items:center;gap:8px;border:1px solid var(--border);
  border-radius:999px;padding:7px 16px;font-size:.82rem;font-weight:600;color:var(--green-hi);
  background:rgba(45,212,168,.07);margin-bottom:22px;
}
.badge .dot{width:7px;height:7px;border-radius:50%;background:var(--green-hi);box-shadow:0 0 10px var(--green-hi);animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
h1{font-size:clamp(2.2rem,4.6vw,3.4rem);font-weight:800;margin-bottom:20px}
.grad{background:linear-gradient(100deg,var(--green-hi) 10%,var(--whats) 90%);-webkit-background-clip:text;background-clip:text;color:transparent}
.hero p.lead{font-size:clamp(1.02rem,1.6vw,1.18rem);color:var(--muted);max-width:34em;margin-bottom:32px}
.hero-cta{display:flex;gap:14px;flex-wrap:wrap;align-items:center}
.hero-note{font-size:.84rem;color:var(--muted);margin-top:14px}
.hero-note strong{color:var(--text)}

/* ── Mock do produto ────────────────────────────────── */
.mock{position:relative;perspective:1200px;margin-bottom:56px}
.mock-card{
  background:linear-gradient(160deg,rgba(255,255,255,.055),rgba(255,255,255,.02));
  border:1px solid var(--border);border-radius:20px;padding:22px;
  box-shadow:0 30px 70px -30px rgba(0,0,0,.7);
  transform:rotateY(-6deg) rotateX(2deg);
}
.mock-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}
.mock-day{font-family:'Sora',sans-serif;font-weight:700;font-size:1.02rem}
.mock-chip{
  font-size:.72rem;font-weight:700;padding:5px 12px;border-radius:999px;
  background:rgba(45,212,168,.12);color:var(--green-hi);border:1px solid rgba(45,212,168,.25);
}
.mock-tags{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0 14px}
.mock-tag{font-size:.74rem;font-weight:600;color:var(--muted);border:1px solid var(--border);border-radius:8px;padding:4px 10px}
.mock-desc{font-size:.86rem;color:var(--muted);border-left:3px solid var(--green);padding-left:12px;margin-bottom:16px}
.mock-chart{
  display:flex;align-items:flex-end;gap:3px;height:62px;margin-bottom:14px;
  padding:8px 10px;background:rgba(255,255,255,.03);
  border:1px solid var(--border);border-radius:12px;
}
.mock-chart i{flex:1;border-radius:3px 3px 0 0;background:var(--green);opacity:.5}
.mock-chart i.hi{background:linear-gradient(180deg,var(--green-hi),var(--green));opacity:1}
.mock-gym{
  margin-top:12px;background:rgba(37,211,102,.05);
  border:1px solid rgba(37,211,102,.2);border-radius:14px;padding:13px 15px;
}
.mock-gym .mg-head{display:flex;align-items:center;gap:8px;font-weight:700;font-size:.84rem;margin-bottom:9px}
.mock-gym .mg-head .mg-dur{margin-left:auto;font-weight:500;font-size:.76rem;color:var(--muted)}
.mock-gym ul{list-style:none;display:grid;gap:5px}
.mock-gym li{font-size:.78rem;color:var(--muted);display:flex;align-items:center;gap:7px}
.mock-gym li b{margin-left:auto;color:var(--text);font-family:'Sora',sans-serif;font-size:.76rem}
.mock-result{background:rgba(45,212,168,.06);border:1px solid rgba(45,212,168,.18);border-radius:14px;padding:14px 16px}
.mock-result .r-title{display:flex;align-items:center;gap:8px;font-weight:700;font-size:.86rem;margin-bottom:8px;color:var(--green-hi)}
.mock-metrics{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:10px}
.mock-metric{font-size:.78rem;color:var(--muted)}
.mock-metric b{display:block;font-size:1.02rem;color:var(--text);font-family:'Sora',sans-serif}
.mock-ai{font-size:.8rem;color:var(--muted);font-style:italic}
.mock-ai b{color:var(--text)}
@keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(-9px)}}
.mock-sync{
  position:absolute;left:-16px;top:-18px;
  background:#0d1f2b;border:1px solid rgba(88,166,255,.3);border-radius:12px;
  padding:9px 14px;font-size:.75rem;font-weight:600;color:#9ecbff;
  box-shadow:0 14px 36px -12px rgba(0,0,0,.6);
  animation:float 6s ease-in-out infinite reverse;
}
.mock-zwo{
  position:absolute;right:-14px;bottom:-16px;z-index:2;
  background:#0b1f18;border:1px solid rgba(45,212,168,.32);border-radius:12px;
  padding:9px 14px;font-size:.75rem;font-weight:600;color:var(--green-hi);
  box-shadow:0 14px 36px -12px rgba(0,0,0,.6);
  animation:float 7s ease-in-out infinite;
}

/* ── Faixa de integrações ───────────────────────────── */
.strip{border-block:1px solid var(--border);background:rgba(255,255,255,.015)}
.strip-inner{display:flex;justify-content:center;gap:clamp(20px,5vw,70px);padding:22px 24px;flex-wrap:wrap}
.strip-item{display:flex;align-items:center;gap:9px;font-size:.9rem;font-weight:600;color:var(--muted)}
.strip-item span{font-size:1.2rem}

/* ── Seções ─────────────────────────────────────────── */
section{padding:92px 0}
.sec-tag{display:block;font-size:.8rem;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--green-hi);margin-bottom:12px;text-align:center}
h2{font-size:clamp(1.7rem,3.4vw,2.4rem);font-weight:800;text-align:center;margin-bottom:14px}
.sec-sub{color:var(--muted);text-align:center;max-width:38em;margin:0 auto 54px;font-size:1.04rem}

/* ── Features ───────────────────────────────────────── */
.features{display:grid;grid-template-columns:repeat(3,1fr);gap:20px}
.feature{
  background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
  padding:28px 26px;transition:transform .25s,border-color .25s,background .25s;
}
.feature:hover{transform:translateY(-5px);border-color:rgba(45,212,168,.4);background:rgba(45,212,168,.045)}
.f-icon{
  width:52px;height:52px;border-radius:14px;display:flex;align-items:center;justify-content:center;
  font-size:1.6rem;margin-bottom:18px;
  background:linear-gradient(140deg,rgba(45,212,168,.16),rgba(18,140,126,.08));
  border:1px solid rgba(45,212,168,.22);
}
.feature h3{font-size:1.08rem;margin-bottom:8px}
.feature p{font-size:.9rem;color:var(--muted)}

/* ── Como funciona ──────────────────────────────────── */
#como{background:linear-gradient(180deg,var(--bg),var(--bg2) 50%,var(--bg))}
.comp-wrap{overflow-x:auto;border:1px solid var(--border);border-radius:16px;background:var(--card)}
.comp{width:100%;border-collapse:collapse;font-size:.93rem;min-width:640px}
.comp th,.comp td{padding:13px 16px;text-align:left;border-bottom:1px solid var(--border)}
.comp thead th{font-size:.78rem;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);font-weight:700}
.comp tbody tr:last-child td{border-bottom:none}
.comp td:first-child{color:var(--muted)}
.comp .comp-nos{background:rgba(45,212,168,.07);color:var(--text)}
.comp thead .comp-nos{color:var(--green-hi);font-weight:800;font-size:.82rem}
.comp .comp-nos b{color:var(--green-hi)}
.comp-mais{display:block;font-size:.78rem;color:var(--muted)}
.comp-nota{max-width:44em;margin:22px auto 0;text-align:center;color:var(--muted);font-size:.95rem;line-height:1.65}
.comp-nota b{color:var(--text)}
@media(max-width:760px){.comp th,.comp td{padding:10px 12px;font-size:.86rem}}
.steps{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;counter-reset:passo}
.step{position:relative;background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:34px 26px 28px}
.step::before{
  counter-increment:passo;content:counter(passo,decimal-leading-zero);
  position:absolute;top:-16px;left:24px;
  font-family:'Sora',sans-serif;font-weight:800;font-size:.95rem;color:#04211a;
  background:linear-gradient(135deg,var(--green-hi),var(--green));
  border-radius:10px;padding:5px 13px;box-shadow:0 8px 20px -6px var(--green-glow);
}
.step h3{font-size:1.06rem;margin-bottom:8px}
.step p{font-size:.9rem;color:var(--muted)}

/* ── Preço ──────────────────────────────────────────── */
.price-card{
  position:relative;max-width:460px;margin:0 auto;border-radius:24px;padding:2px;
  background:linear-gradient(160deg,var(--green-hi),rgba(45,212,168,.12) 40%,rgba(37,211,102,.5));
  box-shadow:0 30px 80px -30px var(--green-glow);
}
.price-inner{background:#0a1712;border-radius:22px;padding:42px 38px;text-align:center}
.price-plan{font-size:.82rem;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:var(--green-hi);margin-bottom:16px}
.price-value{display:flex;align-items:baseline;justify-content:center;gap:6px;margin-bottom:6px}
.price-cur{font-size:1.2rem;font-weight:600;color:var(--muted)}
.price-num{font-family:'Sora',sans-serif;font-size:4rem;font-weight:800;line-height:1}
.price-per{font-size:1rem;color:var(--muted)}
.price-note{font-size:.86rem;color:var(--muted);margin-bottom:28px}
.price-list{list-style:none;text-align:left;margin-bottom:32px;display:grid;gap:12px}
.price-list li{display:flex;gap:11px;align-items:flex-start;font-size:.92rem}
.price-list svg{flex-shrink:0;margin-top:3px}
.price-cancel{font-size:.8rem;color:var(--muted);margin-top:14px}

/* ── FAQ ────────────────────────────────────────────── */
.faq{max-width:720px;margin:0 auto;display:grid;gap:12px}
.faq details{background:var(--card);border:1px solid var(--border);border-radius:14px;overflow:hidden;transition:border-color .2s}
.faq details[open]{border-color:rgba(45,212,168,.35)}
.faq summary{
  cursor:pointer;padding:19px 22px;font-weight:600;font-size:.98rem;list-style:none;
  display:flex;justify-content:space-between;align-items:center;gap:14px;
}
.faq summary::-webkit-details-marker{display:none}
.faq summary::after{content:"+";font-size:1.4rem;color:var(--green-hi);transition:transform .25s;line-height:1}
.faq details[open] summary::after{transform:rotate(45deg)}
.faq .faq-body{padding:0 22px 20px;font-size:.92rem;color:var(--muted)}

/* ── CTA final ──────────────────────────────────────── */
.final{
  text-align:center;border-radius:26px;padding:70px 30px;position:relative;overflow:hidden;
  background:radial-gradient(600px 300px at 50% -40%,rgba(45,212,168,.22),transparent 70%),var(--bg2);
  border:1px solid var(--border);
}
.final h2{margin-bottom:12px}
.final p{color:var(--muted);margin-bottom:30px}

/* ── Footer ─────────────────────────────────────────── */
footer{border-top:1px solid var(--border);padding:34px 0;margin-top:40px}
.foot{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap;font-size:.85rem;color:var(--muted)}
.foot .brand{font-size:1rem}

/* ── Reveal on scroll ───────────────────────────────── */
.reveal{opacity:0;transform:translateY(26px);transition:opacity .6s ease,transform .6s ease}
.reveal.on{opacity:1;transform:none}
@media (prefers-reduced-motion:reduce){
  .reveal{opacity:1;transform:none;transition:none}
  .mock-sync,.badge .dot{animation:none}
  html{scroll-behavior:auto}
}

/* ── Responsivo ─────────────────────────────────────── */
@media (max-width:960px){
  .hero-grid{grid-template-columns:1fr;gap:70px}
  .mock-card{transform:none}
  .features,.steps{grid-template-columns:1fr 1fr}
}
@media (max-width:640px){
  .nav-inner{gap:12px;padding:12px 16px}
  .nav-links{display:none}
  .nav-cta{flex:1;justify-content:flex-end}
  .brand{font-size:1rem}
  .brand .bike{font-size:1.25rem}
  .nav-cta .btn{padding:9px 14px;font-size:.84rem}
  .hero{padding-top:110px}
  .features,.steps{grid-template-columns:1fr}
  section{padding:66px 0}
  .mock-sync{left:0}
  .mock-zwo{right:0}
  .price-inner{padding:34px 24px}
}
</style>
</head>
<body>

<nav id="nav">
  <div class="nav-inner">
    <a class="brand" href="/"><span class="bike">🚵</span> MTB Nutrition</a>
    <div class="nav-links">
      <a href="#recursos">Recursos</a>
      <a href="#como">Como funciona</a>
      <a href="#comparativo">Comparativo</a>
      <a href="#preco">Preço</a>
      <a href="#faq">FAQ</a>
    </div>
    <div class="nav-cta">
      <a class="btn btn-ghost" href="/login">Entrar</a>
      <a class="btn btn-primary" href="/signup">Testar grátis</a>
    </div>
  </div>
</nav>

<header class="hero">
  <div class="wrap hero-grid">
    <div>
      <span class="badge"><span class="dot"></span> Garmin + Inteligência Artificial</span>
      <h1>As outras plataformas te dão a planilha. <span class="grad">Aqui a semana chega pronta.</span></h1>
      <p class="lead">TrainingPeaks e Intervals.icu mostram o que você fez — mas quem decide o treino de amanhã ainda é você, ou um treinador de R$ 300 por mês. Aqui a IA monta a semana inteira, manda pro seu Garmin (ou pro rolo, em .zwo), analisa cada pedalada e recalibra a próxima. Sua parte é uma só: treinar.</p>
      <div class="hero-cta">
        <a class="btn btn-primary btn-lg" href="/signup">Testar 14 dias grátis</a>
        <a class="btn btn-ghost btn-lg" href="#recursos">Ver recursos</a>
      </div>
      <p class="hero-note">Sem cartão. Depois, <strong>R$ 24,99/mês no Pix</strong> — mês a mês, sem fidelidade.</p>
    </div>

    <div class="mock reveal">
      <div class="mock-sync">🔄 Sincronizado do Garmin há 12 min</div>
      <div class="mock-zwo">⬇ treino.zwo pronto para o rolo</div>
      <div class="mock-card">
        <div class="mock-head">
          <span class="mock-day">Terça · VO2max 🔥</span>
          <span class="mock-chip">Semana de choque</span>
        </div>
        <div class="mock-tags">
          <span class="mock-tag">⏱ 1h15</span>
          <span class="mock-tag">📏 32 km</span>
          <span class="mock-tag">⛰ 520 m</span>
          <span class="mock-tag">🔁 90–100 rpm</span>
          <span class="mock-tag">⚡ 96 TSS</span>
        </div>
        <div class="mock-chart" aria-hidden="true">
          <i style="height:22%"></i><i style="height:30%"></i><i style="height:38%"></i><i style="height:46%"></i>
          <i class="hi" style="height:92%"></i><i style="height:34%"></i>
          <i class="hi" style="height:95%"></i><i style="height:34%"></i>
          <i class="hi" style="height:90%"></i><i style="height:34%"></i>
          <i class="hi" style="height:94%"></i><i style="height:34%"></i>
          <i class="hi" style="height:91%"></i><i style="height:34%"></i>
          <i class="hi" style="height:96%"></i>
          <i style="height:40%"></i><i style="height:30%"></i><i style="height:22%"></i>
        </div>
        <p class="mock-desc">6x 3min Z5 (recuperação 5min Z2 entre tiros). Aquecimento 15min progressivo.</p>
        <div class="mock-result">
          <div class="r-title">✅ Concluído — análise da IA</div>
          <div class="mock-metrics">
            <div class="mock-metric"><b>158</b> FC média</div>
            <div class="mock-metric"><b>245 W</b> potência</div>
            <div class="mock-metric"><b>94 rpm</b> cadência</div>
            <div class="mock-metric"><b>98</b> TSS real</div>
          </div>
          <p class="mock-ai"><b>Ponto forte:</b> tiros consistentes, potência estável do 1º ao 6º. Amanhã é regenerativo: pega leve.</p>
        </div>
        <div class="mock-gym">
          <div class="mg-head">🏋️ Academia · manhã <span class="mg-dur">45 min</span></div>
          <ul>
            <li>✅ Agachamento livre — 3x8 <b>60 kg</b></li>
            <li>✅ Levantamento terra — 3x6 <b>70 kg</b></li>
            <li>⬜ Afundo com halteres — 3x10</li>
          </ul>
        </div>
      </div>
    </div>
  </div>
</header>

<div class="strip">
  <div class="strip-inner">
    <div class="strip-item"><span>⌚</span> Integrado ao Garmin Connect</div>
    <div class="strip-item"><span>🏠</span> Rolo: MyWhoosh, Zwift, TrainerRoad</div>
    <div class="strip-item"><span>🏋️</span> Bike + academia na mesma semana</div>
    <div class="strip-item"><span>🏁</span> Periodização por prova</div>
  </div>
</div>

<section id="recursos">
  <div class="wrap">
    <span class="sec-tag">Recursos</span>
    <h2>Tudo o que a sua temporada pede, <span class="grad">num lugar só</span></h2>
    <p class="sec-sub">Chega de planilha no Excel, treino copiado da internet e semana montada no escuro.</p>
    <div class="features">
      <div class="feature reveal">
        <div class="f-icon">🗓️</div>
        <h3>A semana montada por IA</h3>
        <p>A cada semana, a IA olha seu histórico, seu objetivo e as provas no horizonte — e desenha os próximos sete dias sob medida, pedal e academia. Se der dia duplo, cada sessão ganha seu próprio card, em períodos diferentes. Você começa a segunda com tudo pronto.</p>
      </div>
      <div class="feature reveal">
        <div class="f-icon">🚴</div>
        <h3>Do rolo à trilha, você escolhe</h3>
        <p>MTB, speed ou gravel; na rua ou no rolo interativo. Cada dia, você decide onde pedalar — e a IA molda a sessão para a modalidade e o ambiente. A mesma cabeça, seja no asfalto ou na sala de casa.</p>
      </div>
      <div class="feature reveal">
        <div class="f-icon">🏋️</div>
        <h3>A academia entra na conta</h3>
        <p>Diga quantos dias por semana você levanta peso e a IA encaixa a musculação sem atrapalhar o pedal — nunca na véspera de um treino forte. Cada sessão vem com checklist de exercícios, e o peso que você registra hoje é o ponto de partida da semana que vem.</p>
      </div>
      <div class="feature reveal">
        <div class="f-icon">🏠</div>
        <h3>Seu rolo, sem depender do relógio</h3>
        <p>Um clique baixa o treino do dia em .zwo e ele abre no MyWhoosh, Zwift, TrainerRoad ou Rouvy — com os blocos e a potência calculados a partir do <em>seu</em> FTP. Rolo ligado, treino na tela, zero configuração manual.</p>
      </div>
      <div class="feature reveal">
        <div class="f-icon">⌚</div>
        <h3>O treino já está no relógio</h3>
        <p>A semana cai direto no Garmin, com zonas, blocos e cadência estruturados. Terminou de pedalar? A atividade volta sozinha para o portal — sem exportar nada.</p>
      </div>
      <div class="feature reveal">
        <div class="f-icon">🤖</div>
        <h3>A IA lê cada pedalada</h3>
        <p>FC, potência, cadência, TSS, execução — nada passa batido. Depois de cada treino, você recebe o que foi bem, o que ajustar e o próximo passo, em português de gente. Cinta cardíaca falhou? O sistema percebe e refaz a avaliação sem ela.</p>
      </div>
      <div class="feature reveal">
        <div class="f-icon">📊</div>
        <h3>Seu quartel-general</h3>
        <p>Plano da semana, análises, calendário de provas e sua evolução — tudo num painel limpo, aberto de qualquer tela, a qualquer hora.</p>
      </div>
      <div class="feature reveal">
        <div class="f-icon">🏁</div>
        <h3>A prova no comando</h3>
        <p>Cadastre suas provas e a periodização se vira sozinha: base, build, pico e polimento na hora certa — com a estratégia de nutrição pronta para o dia D.</p>
      </div>
      <div class="feature reveal">
        <div class="f-icon">🧠</div>
        <h3>Um assistente que te conhece</h3>
        <p>Ele sabe seu histórico de cor. Peça para remexer a semana, tire uma dúvida de treino ou conte como foi o pedal de ontem — são 5 perguntas por semana, a qualquer hora do dia ou da noite.</p>
      </div>
    </div>
  </div>
</section>

<section id="como">
  <div class="wrap">
    <span class="sec-tag">Como funciona</span>
    <h2>Do cadastro ao pódio em <span class="grad">3 passos</span></h2>
    <p class="sec-sub">Configuração única de 5 minutos. Depois disso, o sistema trabalha por você.</p>
    <div class="steps">
      <div class="step reveal">
        <h3>Conecte o Garmin</h3>
        <p>Cadastro feito, você já está dentro — 14 dias grátis, sem cartão. Conecte o Garmin e a gente importa seus últimos 90 dias: o app já nasce com o seu histórico, e o seu FTP sai da sua melhor pedalada, sem você fazer teste nenhum.</p>
      </div>
      <div class="step reveal">
        <h3>Sua semana aparece pronta</h3>
        <p>A IA desenha os sete dias — pedal e academia — e manda tudo para o seu Garmin. Sem relógio? Baixe o treino em .zwo e abra no rolo. Você só escolhe onde treinar.</p>
      </div>
      <div class="step reveal">
        <h3>Treine — o resto é com a gente</h3>
        <p>Fechou o treino, a IA disseca a atividade, aponta a evolução e recalibra a carga — inclusive o peso que você vai levantar na próxima. Chegando a prova, a estratégia de nutrição chega junto.</p>
      </div>
    </div>
  </div>
</section>

<section id="comparativo">
  <div class="wrap">
    <span class="sec-tag">Comparativo</span>
    <h2>Planilha inteligente <span class="grad">não é treinador</span></h2>
    <p class="sec-sub">As plataformas de referência são excelentes no que fazem — analisar. Nenhuma delas decide o seu treino de amanhã.</p>
    <div class="comp-wrap reveal">
      <table class="comp">
        <thead>
          <tr>
            <th></th>
            <th class="comp-nos">MTB Nutrition</th>
            <th>TrainingPeaks</th>
            <th>Intervals.icu</th>
          </tr>
        </thead>
        <tbody>
          <tr><td>Monta a sua semana sozinho</td><td class="comp-nos"><b>Sim, com IA</b></td><td>Não — coach ou plano à parte</td><td>Não — você monta</td></tr>
          <tr><td>Manda o treino pro Garmin</td><td class="comp-nos">Sim</td><td>Sim</td><td>Sim</td></tr>
          <tr><td>Analisa cada pedalada</td><td class="comp-nos">Sim, com nota e leitura</td><td>Sim, números</td><td>Sim, números</td></tr>
          <tr><td>Recalibra a próxima semana</td><td class="comp-nos"><b>Automático</b></td><td>Só com coach</td><td>Não</td></tr>
          <tr><td>Academia junto do pedal</td><td class="comp-nos">Sim, com carga progressiva</td><td>Parcial</td><td>Não</td></tr>
          <tr><td>O que comer em cada dia</td><td class="comp-nos"><b>Sim, periodizado</b></td><td>Não</td><td>Não</td></tr>
          <tr><td>Fala com você no WhatsApp</td><td class="comp-nos">Sim</td><td>Não</td><td>Não</td></tr>
          <tr><td>Em português, pagando em real</td><td class="comp-nos">Sim, no Pix</td><td>Não</td><td>Não</td></tr>
          <tr><td>Preço por mês</td><td class="comp-nos"><b>R$ 24,99</b></td><td>~R$ 110 <span class="comp-mais">+ coach</span></td><td>Grátis</td></tr>
        </tbody>
      </table>
    </div>
    <p class="comp-nota">O Intervals.icu é gratuito e tecnicamente excelente — se o que você quer é <b>estudar</b> os seus números, use ele. Se o que você quer é <b>não ter que decidir</b> o treino de amanhã, é aqui.</p>
  </div>
</section>

<section id="preco">
  <div class="wrap">
    <span class="sec-tag">Preço</span>
    <h2>Um plano, <span class="grad">tudo dentro</span></h2>
    <p class="sec-sub">Menos que um tubo de gel por semana. Pix, sem taxa de adesão e sem letra miúda.</p>
    <div class="price-card reveal">
      <div class="price-inner">
        <div class="price-plan">Plano Atleta</div>
        <div class="price-value">
          <span class="price-cur">R$</span>
          <span class="price-num">24,99</span>
          <span class="price-per">/mês</span>
        </div>
        <p class="price-note">Pagamento no Pix · mês a mês, sem renovação automática</p>
        <ul class="price-list">
          <li><svg width="18" height="18" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="11" fill="rgba(45,212,168,.15)"/><path d="M7 12.5l3.2 3.2L17 9" stroke="#2dd4a8" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg> Planilha de treinos semanal personalizada</li>
          <li><svg width="18" height="18" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="11" fill="rgba(45,212,168,.15)"/><path d="M7 12.5l3.2 3.2L17 9" stroke="#2dd4a8" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg> Envio automático dos treinos para o Garmin</li>
          <li><svg width="18" height="18" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="11" fill="rgba(45,212,168,.15)"/><path d="M7 12.5l3.2 3.2L17 9" stroke="#2dd4a8" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg> Análise pós-treino com IA ilimitada</li>
          <li><svg width="18" height="18" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="11" fill="rgba(45,212,168,.15)"/><path d="M7 12.5l3.2 3.2L17 9" stroke="#2dd4a8" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg> Nutrição periodizada + guia de prova</li>
          <li><svg width="18" height="18" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="11" fill="rgba(45,212,168,.15)"/><path d="M7 12.5l3.2 3.2L17 9" stroke="#2dd4a8" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg> Treinos para MTB, estrada, gravel e rolo — indoor ou outdoor</li>
          <li><svg width="18" height="18" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="11" fill="rgba(45,212,168,.15)"/><path d="M7 12.5l3.2 3.2L17 9" stroke="#2dd4a8" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg> Academia planejada pela IA, com checklist e progressão de carga</li>
          <li><svg width="18" height="18" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="11" fill="rgba(45,212,168,.15)"/><path d="M7 12.5l3.2 3.2L17 9" stroke="#2dd4a8" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg> Download em .zwo para MyWhoosh, Zwift e TrainerRoad</li>
          <li><svg width="18" height="18" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="11" fill="rgba(45,212,168,.15)"/><path d="M7 12.5l3.2 3.2L17 9" stroke="#2dd4a8" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg> Assistente IA com o seu histórico — 5 perguntas por semana</li>
        </ul>
        <a class="btn btn-primary btn-lg" href="/signup" style="width:100%">Começar 14 dias grátis</a>
        <p class="price-cancel">Comece com <b>14 dias grátis</b> — sem cartão, sem cobrança automática. Depois do teste, o QR code Pix fica no portal: você paga, manda o comprovante no WhatsApp e o acesso é liberado. Ao assinar você concorda com os <a href="/termos" style="color:var(--green-hi)">termos de uso</a> e a <a href="/privacidade" style="color:var(--green-hi)">política de privacidade</a>.</p>
      </div>
    </div>
  </div>
</section>

<section id="faq">
  <div class="wrap">
    <span class="sec-tag">FAQ</span>
    <h2>Perguntas frequentes</h2>
    <p class="sec-sub">O que todo mundo pergunta antes de assinar.</p>
    <div class="faq">
      <details class="reveal">
        <summary>Preciso ter um Garmin para usar?</summary>
        <div class="faq-body">Para treinar, não. Todo treino tem um botão que baixa o arquivo .zwo — o formato que os apps de rolo entendem. Você importa no MyWhoosh (que é gratuito), Zwift, TrainerRoad ou Rouvy e pedala com os blocos e a potência já calculados a partir do seu FTP.<br><br>Para a análise pós-treino, o sistema precisa receber a atividade de volta. O caminho mais simples é ligar o app do rolo ao Garmin Connect — a conta é gratuita e não exige nenhum aparelho: a pedalada cai lá e o nosso sync analisa igual, sem você mexer em nada. E se você treinou sem nada registrando, é só contar ao assistente que ele anota a sessão no seu histórico.</div>
      </details>
      <details class="reveal">
        <summary>Posso treinar indoor e outdoor?</summary>
        <div class="faq-body">Sim. Os treinos funcionam para MTB, estrada e gravel, e você escolhe onde pedalar em cada dia: na rua (outdoor) ou no rolo (indoor). No indoor a prescrição vira watts, e o download em .zwo abre direto no MyWhoosh, Zwift ou TrainerRoad — o rolo controla a carga para você.</div>
      </details>
      <details class="reveal">
        <summary>Como recebo os treinos?</summary>
        <div class="faq-body">A semana fica no portal e vai para o seu Garmin com um clique, com zonas, cadência e etapas estruturadas — é só sincronizar o relógio e pedalar. Para o rolo, o mesmo treino sai em .zwo. Cada sessão ainda mostra o gráfico dos blocos e o TSS previsto, para você saber o tamanho do caldo antes de subir na bike.</div>
      </details>
      <details class="reveal">
        <summary>A análise por IA funciona como?</summary>
        <div class="faq-body">Ao concluir um treino, o sistema baixa a atividade, compara o executado com o planejado (FC, potência, cadência, zonas) e gera uma análise com pontos fortes e pontos a melhorar — em linguagem simples, sem tecniquês.</div>
      </details>
      <details class="reveal">
        <summary>Vocês montam treino de academia também?</summary>
        <div class="faq-body">Sim. Você informa quantos dias por semana treina força e em que períodos, e a IA encaixa a musculação na semana respeitando o pedal — nunca na véspera nem no dia seguinte de um treino forte, e no mesmo dia só junto de pedal leve. Cada sessão vem com a lista de exercícios em formato de checklist: você marca o que fez e anota o peso, e a carga registrada vira o ponto de partida da semana seguinte.</div>
      </details>
      <details class="reveal">
        <summary>E se a cinta cardíaca falhar no meio do treino?</summary>
        <div class="faq-body">O sistema percebe. Quando os dados de frequência cardíaca vêm inconsistentes, a análise é refeita ignorando a FC e usando o que é confiável — potência, cadência, tempo em cada bloco. Você não recebe um diagnóstico errado por causa de uma cinta sem bateria.</div>
      </details>
      <details class="reveal">
        <summary>Serve para quem está começando?</summary>
        <div class="faq-body">Sim. O plano é montado a partir do seu perfil e evolui com você: iniciantes recebem mais base e técnica; quem já compete recebe periodização focada nas provas do calendário. Na academia vale o mesmo — a carga de entrada respeita o seu nível e sobe a partir do que você levantou de verdade.</div>
      </details>
      <details class="reveal">
        <summary>Como funciona o teste grátis?</summary>
        <div class="faq-body">Você se cadastra e entra na hora — 14 dias com tudo liberado, sem cartão e sem cobrança automática. São 14 e não 7 de propósito: o que essa plataforma faz de diferente é <b>recalibrar a semana seguinte</b> a partir do que você executou, e isso só acontece na virada da semana. Em 7 dias você decidiria antes de ver a parte que importa.</div>
      </details>
      <details class="reveal">
        <summary>Como funciona o pagamento?</summary>
        <div class="faq-body">Só por Pix. Terminado o teste, o QR code (e o código copia-e-cola) de R$ 24,99 fica no portal, em <b>Assinatura</b>. Você paga, envia o comprovante pelo WhatsApp e a gente libera 30 dias de acesso — normalmente no mesmo dia. Não pedimos cartão em momento nenhum.<br><br>Pagando antes do teste acabar, os dias que sobraram entram de bônus: você não perde nada por assinar cedo.</div>
      </details>
      <details class="reveal">
        <summary>E se eu não assinar depois do teste?</summary>
        <div class="faq-body">Nada é apagado. Você continua conseguindo ver no portal tudo que já treinou — o que para é a parte que gera coisa nova: montar a semana, mandar pro Garmin, baixar o .zwo e conversar com o assistente. Assinou depois, volta tudo exatamente de onde parou.</div>
      </details>
      <details class="reveal">
        <summary>Posso cancelar quando quiser?</summary>
        <div class="faq-body">Sim, e nem precisa avisar. Como o pagamento é por Pix, não existe cobrança automática nem cartão guardado: cada mês é um Pix novo. Se não quiser continuar, é só não pagar o próximo — sem fidelidade, sem multa e sem ter que cancelar nada com ninguém.</div>
      </details>
    </div>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="final reveal">
      <h2>A sua melhor temporada começa numa <span class="grad">segunda-feira</span></h2>
      <p>Bike e academia planejadas por IA, sincronizadas com o relógio ou com o rolo, e analisadas sozinhas. Teste 14 dias — se não valer os R$ 24,99, é só não pagar.</p>
      <a class="btn btn-primary btn-lg" href="/signup">Começar 14 dias grátis</a>
    </div>
  </div>
</section>

<footer>
  <div class="wrap foot">
    <a class="brand" href="/"><span class="bike">🚵</span> MTB Nutrition</a>
    <div>Treino inteligente gerado por IA para ciclistas — bike e academia, do MTB ao rolo.</div>
    <div><a href="/login" style="color:var(--green-hi)">Entrar</a> · <a href="/signup" style="color:var(--green-hi)">Criar conta</a> · <a href="/termos" style="color:var(--green-hi)">Termos de uso</a> · <a href="/privacidade" style="color:var(--green-hi)">Privacidade</a></div>
    <div style="font-size:.78rem;opacity:.75;max-width:640px;margin:6px auto 0;line-height:1.55">
      ⚕️ Os treinos e cardápios são gerados por inteligência artificial e têm caráter informativo.
      Não substituem avaliação médica, nutricionista (CFN) nem profissional de educação física (CREF).
      Consulte um profissional antes de iniciar.
    </div>
  </div>
</footer>

<script>
(function(){
  var nav = document.getElementById('nav');
  function onScroll(){ nav.classList.toggle('scrolled', window.scrollY > 10); }
  window.addEventListener('scroll', onScroll, {passive:true});
  onScroll();

  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function(entries){
      entries.forEach(function(e){
        if(e.isIntersecting){ e.target.classList.add('on'); io.unobserve(e.target); }
      });
    }, {threshold:.12});
    document.querySelectorAll('.reveal').forEach(function(el){ io.observe(el); });
  } else {
    document.querySelectorAll('.reveal').forEach(function(el){ el.classList.add('on'); });
  }
})();
</script>
</body>
</html>"""
