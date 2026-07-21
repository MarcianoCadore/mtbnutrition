"""Landing page pública do MTB Nutrition.

Servida em `/` para visitantes não autenticados (usuários logados são
redirecionados ao portal pelo handler em main.py).
"""

LANDING_HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MTB Nutrition — Treino de MTB gerado por IA, no piloto automático</title>
<meta name="description" content="Sua semana de treino de MTB gerada por IA, sincronizada com o Garmin e com análise pós-treino automática, tudo no seu WhatsApp. Assine por R$ 24,99/mês.">
<meta property="og:title" content="MTB Nutrition — Treino de MTB gerado por IA, no piloto automático">
<meta property="og:description" content="Garmin + IA + WhatsApp: a IA monta sua semana de treino, sincroniza com o relógio e analisa cada pedalada. R$ 24,99/mês.">
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
.mock-result{background:rgba(45,212,168,.06);border:1px solid rgba(45,212,168,.18);border-radius:14px;padding:14px 16px}
.mock-result .r-title{display:flex;align-items:center;gap:8px;font-weight:700;font-size:.86rem;margin-bottom:8px;color:var(--green-hi)}
.mock-metrics{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:10px}
.mock-metric{font-size:.78rem;color:var(--muted)}
.mock-metric b{display:block;font-size:1.02rem;color:var(--text);font-family:'Sora',sans-serif}
.mock-ai{font-size:.8rem;color:var(--muted);font-style:italic}
.mock-ai b{color:var(--text)}
.mock-whats{
  position:absolute;right:-14px;bottom:-88px;max-width:270px;
  background:#0f2b22;border:1px solid rgba(37,211,102,.35);border-radius:16px 16px 4px 16px;
  padding:13px 16px;font-size:.8rem;color:#d7f5e6;
  box-shadow:0 18px 44px -14px rgba(0,0,0,.65);
  animation:float 5s ease-in-out infinite;
}
.mock-whats .w-head{display:flex;align-items:center;gap:7px;font-weight:700;color:var(--whats);margin-bottom:5px;font-size:.78rem}
@keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(-9px)}}
.mock-sync{
  position:absolute;left:-16px;top:-18px;
  background:#0d1f2b;border:1px solid rgba(88,166,255,.3);border-radius:12px;
  padding:9px 14px;font-size:.75rem;font-weight:600;color:#9ecbff;
  box-shadow:0 14px 36px -12px rgba(0,0,0,.6);
  animation:float 6s ease-in-out infinite reverse;
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
  .mock-whats,.mock-sync,.badge .dot{animation:none}
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
  .mock-whats{right:0;bottom:-92px}
  .mock-sync{left:0}
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
      <a href="#preco">Preço</a>
      <a href="#faq">FAQ</a>
    </div>
    <div class="nav-cta">
      <a class="btn btn-ghost" href="/login">Entrar</a>
      <a class="btn btn-primary" href="/signup">Criar conta</a>
    </div>
  </div>
</nav>

<header class="hero">
  <div class="wrap hero-grid">
    <div>
      <span class="badge"><span class="dot"></span> Garmin + IA + WhatsApp</span>
      <h1>Treino de MTB gerado por <span class="grad">IA</span>, no piloto automático</h1>
      <p class="lead">A IA monta sua semana de treino, manda direto pro Garmin e analisa cada pedalada no seu WhatsApp. Você só precisa pedalar.</p>
      <div class="hero-cta">
        <a class="btn btn-primary btn-lg" href="/signup">Assinar por R$ 24,99/mês</a>
        <a class="btn btn-ghost btn-lg" href="#recursos">Ver recursos</a>
      </div>
      <p class="hero-note">Sem fidelidade — <strong>cancele quando quiser</strong>.</p>
    </div>

    <div class="mock reveal">
      <div class="mock-sync">🔄 Sincronizado do Garmin há 12 min</div>
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
        </div>
        <p class="mock-desc">6x 3min Z5 (recuperação 5min Z2 entre tiros). Aquecimento 15min progressivo.</p>
        <div class="mock-result">
          <div class="r-title">✅ Concluído — análise da IA</div>
          <div class="mock-metrics">
            <div class="mock-metric"><b>158</b> FC média</div>
            <div class="mock-metric"><b>245 W</b> potência</div>
            <div class="mock-metric"><b>94 rpm</b> cadência</div>
          </div>
          <p class="mock-ai"><b>Ponto forte:</b> tiros consistentes, potência estável do 1º ao 6º. Amanhã é regenerativo: capriche no carboidrato hoje à noite.</p>
        </div>
      </div>
      <div class="mock-whats">
        <div class="w-head">💬 WhatsApp · MTB Nutrition</div>
        📅 Sua semana está pronta! A IA gerou 5 treinos personalizados e já mandei pro seu Garmin. Bora pedalar? 🚵
      </div>
    </div>
  </div>
</header>

<div class="strip">
  <div class="strip-inner">
    <div class="strip-item"><span>⌚</span> Integrado ao Garmin Connect</div>
    <div class="strip-item"><span>🤖</span> Treino semanal gerado por IA</div>
    <div class="strip-item"><span>💬</span> Alertas no WhatsApp</div>
    <div class="strip-item"><span>🏁</span> Periodização por prova</div>
  </div>
</div>

<section id="recursos">
  <div class="wrap">
    <span class="sec-tag">Recursos</span>
    <h2>Tudo que o seu treino de MTB precisa, <span class="grad">num lugar só</span></h2>
    <p class="sec-sub">Chega de planilha no Excel, cardápio genérico e treino perdido no meio do grupo do zap.</p>
    <div class="features">
      <div class="feature reveal">
        <div class="f-icon">🗓️</div>
        <h3>Sua semana de treino, gerada por IA</h3>
        <p>Toda semana a IA monta sua planilha de treino personalizada, considerando seu histórico, objetivo e as provas do seu calendário. Você só recebe e pedala.</p>
      </div>
      <div class="feature reveal">
        <div class="f-icon">⌚</div>
        <h3>Sincronização Garmin automática</h3>
        <p>Os treinos da semana são enviados direto para o seu Garmin, com zonas, cadência e etapas estruturadas. Terminou de pedalar? A atividade volta sozinha para o portal.</p>
      </div>
      <div class="feature reveal">
        <div class="f-icon">🤖</div>
        <h3>Análise pós-treino com IA</h3>
        <p>Cada pedalada é analisada: FC, potência, cadência e execução. Você recebe pontos fortes, pontos a melhorar e o que ajustar no próximo treino.</p>
      </div>
      <div class="feature reveal">
        <div class="f-icon">💬</div>
        <h3>Tudo no seu WhatsApp</h3>
        <p>Plano de treino, análise pós-pedalada e alertas de prova chegam direto no seu zap. Sem precisar abrir mais um app.</p>
      </div>
      <div class="feature reveal">
        <div class="f-icon">🏁</div>
        <h3>Calendário de provas</h3>
        <p>Cadastre suas provas e a periodização se organiza sozinha: base, build, pico e polimento — com foco semanal e estratégia de nutrição para o dia da prova.</p>
      </div>
      <div class="feature reveal">
        <div class="f-icon">🧠</div>
        <h3>Assistente 24/7</h3>
        <p>Um assistente com IA que conhece o seu histórico: pergunte sobre treino, peça para remarcar a semana ou tire dúvidas a qualquer hora.</p>
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
        <h3>Crie sua conta e conecte o Garmin</h3>
        <p>Informe seu perfil (idade, peso, FTP, zonas de FC) e conecte sua conta Garmin Connect. Pronto — a integração é automática dali em diante.</p>
      </div>
      <div class="step reveal">
        <h3>Receba sua semana de treino, gerada por IA</h3>
        <p>A planilha da semana é montada pela IA e vai direto para o seu relógio. O cardápio do dia também chega no WhatsApp, ajustado ao treino.</p>
      </div>
      <div class="step reveal">
        <h3>Pedale — o resto é com a gente</h3>
        <p>Terminou o treino, a IA analisa a atividade, aponta evolução e ajusta a carga. Antes da prova, você recebe a estratégia completa de nutrição.</p>
      </div>
    </div>
  </div>
</section>

<section id="preco">
  <div class="wrap">
    <span class="sec-tag">Preço</span>
    <h2>Um plano único, <span class="grad">tudo incluso</span></h2>
    <p class="sec-sub">Menos que um tubo de gel por semana. Sem taxa de adesão, sem surpresa.</p>
    <div class="price-card reveal">
      <div class="price-inner">
        <div class="price-plan">Plano Atleta</div>
        <div class="price-value">
          <span class="price-cur">R$</span>
          <span class="price-num">24,99</span>
          <span class="price-per">/mês</span>
        </div>
        <p class="price-note">Cobrança mensal · cancele quando quiser</p>
        <ul class="price-list">
          <li><svg width="18" height="18" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="11" fill="rgba(45,212,168,.15)"/><path d="M7 12.5l3.2 3.2L17 9" stroke="#2dd4a8" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg> Planilha de treinos semanal personalizada</li>
          <li><svg width="18" height="18" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="11" fill="rgba(45,212,168,.15)"/><path d="M7 12.5l3.2 3.2L17 9" stroke="#2dd4a8" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg> Envio automático dos treinos para o Garmin</li>
          <li><svg width="18" height="18" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="11" fill="rgba(45,212,168,.15)"/><path d="M7 12.5l3.2 3.2L17 9" stroke="#2dd4a8" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg> Análise pós-treino com IA ilimitada</li>
          <li><svg width="18" height="18" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="11" fill="rgba(45,212,168,.15)"/><path d="M7 12.5l3.2 3.2L17 9" stroke="#2dd4a8" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg> Nutrição periodizada + guia de prova</li>
          <li><svg width="18" height="18" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="11" fill="rgba(45,212,168,.15)"/><path d="M7 12.5l3.2 3.2L17 9" stroke="#2dd4a8" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg> Notificações e lembretes no WhatsApp</li>
          <li><svg width="18" height="18" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="11" fill="rgba(45,212,168,.15)"/><path d="M7 12.5l3.2 3.2L17 9" stroke="#2dd4a8" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg> Assistente IA 24/7 com o seu histórico</li>
        </ul>
        <a class="btn btn-primary btn-lg" href="/signup" style="width:100%">Começar agora</a>
        <p class="price-cancel">Ao assinar você concorda com os termos de uso.</p>
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
        <div class="faq-body">O Garmin deixa tudo automático (treino vai para o relógio, atividade volta sozinha), mas não é obrigatório: você pode acompanhar a planilha pelo portal e enviar seus arquivos .fit manualmente para receber a análise da IA.</div>
      </details>
      <details class="reveal">
        <summary>Como recebo os treinos e o cardápio?</summary>
        <div class="faq-body">A semana de treinos fica no portal e é enviada ao seu Garmin com um clique. O plano alimentar do dia e os lembretes chegam no seu WhatsApp, sempre ajustados ao treino daquele dia.</div>
      </details>
      <details class="reveal">
        <summary>A análise por IA funciona como?</summary>
        <div class="faq-body">Ao concluir um treino, o sistema baixa a atividade, compara o executado com o planejado (FC, potência, cadência, zonas) e gera uma análise com pontos fortes e pontos a melhorar — em linguagem simples, sem tecniquês.</div>
      </details>
      <details class="reveal">
        <summary>Posso cancelar quando quiser?</summary>
        <div class="faq-body">Sim. A assinatura é mensal, sem fidelidade e sem multa. Cancelou, não é mais cobrado no mês seguinte.</div>
      </details>
      <details class="reveal">
        <summary>Serve para quem está começando no MTB?</summary>
        <div class="faq-body">Sim. O plano é montado a partir do seu perfil e evolui com você: iniciantes recebem mais base e técnica; quem já compete recebe periodização focada nas provas do calendário.</div>
      </details>
    </div>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="final reveal">
      <h2>Pronto para evoluir no <span class="grad">MTB</span>?</h2>
      <p>Sua semana de treino gerada por IA, sincronizada com o relógio e analisada no zap — por menos de R$ 0,85 por dia.</p>
      <a class="btn btn-primary btn-lg" href="/signup">Assinar por R$ 24,99/mês</a>
    </div>
  </div>
</section>

<footer>
  <div class="wrap foot">
    <a class="brand" href="/"><span class="bike">🚵</span> MTB Nutrition</a>
    <div>Treino inteligente gerado por IA para ciclistas de MTB.</div>
    <div><a href="/login" style="color:var(--green-hi)">Entrar</a> · <a href="/signup" style="color:var(--green-hi)">Criar conta</a></div>
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
