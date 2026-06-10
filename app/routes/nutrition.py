from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from datetime import datetime
from app.models.models import PlanoAlimentar, Treino
from app.services.ai_service import gerar_plano_alimentar
from pydantic import BaseModel
from app.services.nutricao_service import plano_para_tipo, tabela_alimentos, guia_refeicoes, TIPO_PARA_MENU
from app.services.config_service import get_horarios, salvar_horarios
from app.services.mongo_service import get_db

router = APIRouter()


@router.get("/plano/{tipo}")
async def plano_por_tipo(tipo: str, data: str | None = None):
    """Cardápio do tipo de treino para uma data (varia a cada dia) — usado nos cards."""
    cfg = await get_horarios()
    return plano_para_tipo(tipo, data, cfg)


class HorariosBody(BaseModel):
    cafe: str | None = None
    almoco: str | None = None
    lanche_tarde: str | None = None
    jantar: str | None = None


@router.get("/horarios")
async def ler_horarios():
    return await get_horarios()


@router.post("/horarios")
async def gravar_horarios(body: HorariosBody):
    try:
        cfg = await salvar_horarios(body.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # reagenda os lembretes de refeição para os novos horários
    from app.tasks.scheduler import agendar_lembretes_refeicao
    await agendar_lembretes_refeicao()
    return {"status": "salvo", **cfg}


@router.post("/gerar", response_model=dict)
async def gerar_plano(treino: Treino | None = None):
    plano = await gerar_plano_alimentar(treino)
    db = get_db()
    await db.planos.insert_one(plano.model_dump())
    return plano.model_dump()


@router.get("/")
async def listar_planos():
    db = get_db()
    planos = await db.planos.find({}, {"_id": 0}).to_list(30)
    return planos


@router.get("/hoje")
async def plano_hoje():
    db = get_db()
    hoje = datetime.now().date()
    doc = await db.planos.find_one(
        {"data": {"$gte": datetime(hoje.year, hoje.month, hoje.day)}},
        {"_id": 0}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Nenhum plano gerado hoje")
    return doc


_TIPO_LABELS = {
    "Z2_LONGO": "🚴 Z2 Longo", "TIROS": "⚡ Tiros", "VO2MAX": "🔥 VO2Max",
    "TEMPO": "💨 Tempo", "FORCA": "💪 Força", "RECUPERACAO": "🌿 Recuperação",
    "DESCANSO": "🛌 Descanso",
}
_ORDEM_TIPOS = ["TIROS", "VO2MAX", "TEMPO", "FORCA", "Z2_LONGO", "RECUPERACAO", "DESCANSO"]


@router.get("/guia", response_class=HTMLResponse)
async def guia_nutricao():
    # tabela de alimentos
    linhas_tab = "".join(
        f"<tr><td>{a['nome']}</td><td class='c'>{a['base']}</td>"
        f"<td class='c'>{a['kcal']}</td><td class='c'>{a['prot']:g}</td></tr>"
        for a in tabela_alimentos()
    )

    # cardápios por tipo
    cfg = await get_horarios()
    blocos = []
    for tipo in _ORDEM_TIPOS:
        p = plano_para_tipo(tipo, None, cfg)
        refs = []
        for r in p["refeicoes"]:
            itens = "".join(
                f"<li><span class='it'>{i['texto']}</span>"
                f"<span class='kc'>{i['kcal']} kcal · {i['proteina_g']:g}g P</span></li>"
                for i in r["itens"]
            )
            refs.append(
                f"<div class='ref'><div class='ref-h'><span>{r['horario']} · {r['nome']}</span>"
                f"<span class='ref-tot'>{r['kcal']} kcal · {r['proteina_g']:g}g P</span></div>"
                f"<ul>{itens}</ul></div>"
            )
        nota = f"<p class='estrat' style='color:#8a5a00'>⏰ {p['nota_treino']}</p>" if p.get("nota_treino") else ""
        blocos.append(
            f"<details class='tipo-bloco'><summary>"
            f"<span class='tipo-nome'>{_TIPO_LABELS.get(tipo, tipo)}</span>"
            f"<span class='tipo-tot'>{p['kcal_total']} kcal · {p['proteina_total_g']:g}g proteína</span>"
            f"</summary>"
            f"<p class='estrat'>💡 {p['estrategia']}</p>"
            f"{nota}"
            f"{''.join(refs)}</details>"
        )

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MTB Nutrition — Guia Alimentar</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{ --green:#0e8a7d; --text:#1f2937; --muted:#6b7280; --border:#e5e7eb; --bg:#f0f2f5; }}
  body {{ font-family:-apple-system,BlinkMacSystemFont,sans-serif; background:var(--bg); color:var(--text); line-height:1.5; }}
  nav {{ background:#fff; border-bottom:1px solid var(--border); padding:14px 20px; display:flex; align-items:center; gap:10px; }}
  nav .logo {{ font-weight:800; color:var(--green); }}
  nav a {{ margin-left:auto; color:var(--muted); text-decoration:none; font-size:.9rem; font-weight:600; }}
  main {{ max-width:760px; margin:0 auto; padding:24px 16px 60px; }}
  h1 {{ font-size:1.5rem; margin-bottom:6px; }}
  .sub {{ color:var(--muted); margin-bottom:24px; }}
  .card {{ background:#fff; border-radius:14px; padding:22px; margin-bottom:20px; box-shadow:0 1px 4px rgba(0,0,0,.06); }}
  .card h2 {{ font-size:1.1rem; margin-bottom:12px; color:var(--green); }}
  .princ {{ list-style:none; }}
  .princ li {{ padding:8px 0; border-bottom:1px solid var(--border); font-size:.92rem; }}
  .princ li:last-child {{ border-bottom:none; }}
  .princ b {{ color:var(--green); }}
  table {{ width:100%; border-collapse:collapse; font-size:.85rem; }}
  th, td {{ padding:7px 8px; border-bottom:1px solid var(--border); text-align:left; }}
  th {{ color:var(--muted); font-size:.72rem; text-transform:uppercase; letter-spacing:.4px; }}
  td.c, th.c {{ text-align:center; }}
  .tipo-bloco {{ background:#fff; border-radius:12px; margin-bottom:12px; box-shadow:0 1px 4px rgba(0,0,0,.06); overflow:hidden; }}
  summary {{ cursor:pointer; padding:16px 18px; display:flex; justify-content:space-between; align-items:center; gap:10px; font-weight:700; list-style:none; }}
  summary::-webkit-details-marker {{ display:none; }}
  .tipo-nome {{ font-size:1rem; }}
  .tipo-tot {{ font-size:.78rem; color:var(--green); font-weight:700; white-space:nowrap; }}
  .estrat {{ padding:0 18px 10px; font-size:.85rem; color:var(--muted); font-style:italic; }}
  .ref {{ padding:10px 18px; border-top:1px solid var(--border); }}
  .ref-h {{ display:flex; justify-content:space-between; align-items:baseline; gap:8px; margin-bottom:6px; }}
  .ref-h span:first-child {{ font-weight:700; font-size:.9rem; }}
  .ref-tot {{ font-size:.72rem; color:var(--muted); font-weight:600; white-space:nowrap; }}
  .ref ul {{ list-style:none; }}
  .ref li {{ display:flex; justify-content:space-between; gap:10px; padding:3px 0; font-size:.84rem; }}
  .ref li .kc {{ color:var(--muted); font-size:.76rem; white-space:nowrap; }}
</style>
</head>
<body>
<nav>
  <span style="font-size:1.4rem">🥗</span>
  <span class="logo">MTB Nutrition</span>
  <a href="/portal/">← Voltar ao portal</a>
</nav>
<main>
  <h1>Guia Alimentar</h1>
  <p class="sub">Perder peso mantendo a potência (melhorar W/kg) — com alimentos básicos.</p>

  <div class="card">
    <h2>Como comer para perder peso sem perder potência</h2>
    <ul class="princ">
      <li><b>Déficit moderado.</b> Coma um pouco abaixo do gasto — nunca passe fome. Déficit agressivo derruba a potência e queima músculo.</li>
      <li><b>Proteína alta e constante (~180–190 g/dia).</b> É o que preserva o músculo enquanto você emagrece. Distribua em todas as refeições.</li>
      <li><b>Carboidrato periodizado.</b> Combustível para o trabalho do dia: <b>mais</b> nos treinos fortes/longos, <b>menos</b> nos dias leves e de descanso. É por isso que o cardápio muda conforme o treino.</li>
      <li><b>Timing.</b> Concentre o carboidrato em volta do treino (antes para ter energia, depois para repor o glicogênio e recuperar).</li>
      <li><b>Verduras e água à vontade.</b> Saciam sem peso calórico. Mínimo 3 L de água/dia.</li>
    </ul>
  </div>

  <div class="card">
    <h2>Tabela de alimentos básicos</h2>
    <table>
      <thead><tr><th>Alimento</th><th class="c">Porção</th><th class="c">kcal</th><th class="c">Proteína (g)</th></tr></thead>
      <tbody>{linhas_tab}</tbody>
    </table>
  </div>

  <p class="sub" style="margin-bottom:14px">👉 Veja também: <a href="/nutrition/alimentos" style="color:var(--green);font-weight:700">O que comer em cada refeição</a></p>

  <h2 style="font-size:1.1rem; margin:24px 4px 6px; color:var(--green)">Cardápios por tipo de treino</h2>
  <p class="sub" style="margin-bottom:12px">🔄 O cardápio varia a cada dia (rotação de alimentos equivalentes) — abaixo um exemplo de cada tipo.</p>
  {''.join(blocos)}
</main>
</body>
</html>"""


@router.get("/alimentos", response_class=HTMLResponse)
async def guia_alimentos():
    blocos = []
    for r in guia_refeicoes():
        linhas = "".join(
            f"<li><span class='it'>{a['nome']}</span>"
            f"<span class='por'>{a['base']}</span>"
            f"<span class='kc'>{a['kcal']} kcal · {a['prot']:g}g P</span></li>"
            for a in r["alimentos"]
        )
        blocos.append(
            f"<div class='card'>"
            f"<div class='ref-head'><span class='ref-hora'>{r['horario']}</span>"
            f"<h2>{r['nome']}</h2></div>"
            f"<p class='papel'>{r['papel']}</p>"
            f"<ul class='lista'>{linhas}</ul>"
            f"<p class='dica'>💡 {r['dica']}</p>"
            f"</div>"
        )

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MTB Nutrition — O que comer em cada refeição</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{ --green:#0e8a7d; --text:#1f2937; --muted:#6b7280; --border:#e5e7eb; --bg:#f0f2f5; }}
  body {{ font-family:-apple-system,BlinkMacSystemFont,sans-serif; background:var(--bg); color:var(--text); line-height:1.5; }}
  nav {{ background:#fff; border-bottom:1px solid var(--border); padding:14px 20px; display:flex; align-items:center; gap:10px; }}
  nav .logo {{ font-weight:800; color:var(--green); }}
  nav a {{ margin-left:auto; color:var(--muted); text-decoration:none; font-size:.9rem; font-weight:600; }}
  main {{ max-width:760px; margin:0 auto; padding:24px 16px 60px; }}
  h1 {{ font-size:1.5rem; margin-bottom:6px; }}
  .sub {{ color:var(--muted); margin-bottom:24px; }}
  .sub a {{ color:var(--green); font-weight:700; }}
  .card {{ background:#fff; border-radius:14px; padding:20px 22px; margin-bottom:16px; box-shadow:0 1px 4px rgba(0,0,0,.06); }}
  .ref-head {{ display:flex; align-items:center; gap:10px; margin-bottom:8px; }}
  .ref-head h2 {{ font-size:1.15rem; color:var(--green); }}
  .ref-hora {{ background:var(--green); color:#fff; font-size:.75rem; font-weight:700; padding:3px 9px; border-radius:20px; }}
  .papel {{ font-size:.9rem; color:var(--text); margin-bottom:12px; }}
  .lista {{ list-style:none; }}
  .lista li {{ display:flex; align-items:baseline; gap:8px; padding:7px 0; border-bottom:1px solid var(--border); font-size:.86rem; }}
  .lista li:last-child {{ border-bottom:none; }}
  .lista .it {{ font-weight:700; flex:1; }}
  .lista .por {{ color:var(--muted); font-size:.76rem; }}
  .lista .kc {{ color:var(--green); font-size:.76rem; font-weight:700; white-space:nowrap; min-width:110px; text-align:right; }}
  .dica {{ margin-top:12px; font-size:.84rem; color:#8a5a00; background:#fff7e6; border-radius:8px; padding:9px 11px; }}
</style>
</head>
<body>
<nav>
  <span style="font-size:1.4rem">🍽️</span>
  <span class="logo">MTB Nutrition</span>
  <a href="/portal/">← Voltar ao portal</a>
</nav>
<main>
  <h1>O que comer em cada refeição</h1>
  <p class="sub">Quando comer cada alimento, com as calorias por porção. Veja também os <a href="/nutrition/guia">cardápios por tipo de treino</a>.</p>
  {''.join(blocos)}
</main>
</body>
</html>"""


@router.get("/config", response_class=HTMLResponse)
async def config_horarios():
    return """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MTB Nutrition — Horários das refeições</title>
<style>
  * { box-sizing:border-box; margin:0; padding:0; }
  :root { --green:#0e8a7d; --text:#1f2937; --muted:#6b7280; --border:#e5e7eb; --bg:#f0f2f5; }
  body { font-family:-apple-system,BlinkMacSystemFont,sans-serif; background:var(--bg); color:var(--text); }
  nav { background:#fff; border-bottom:1px solid var(--border); padding:14px 20px; display:flex; align-items:center; gap:10px; }
  nav .logo { font-weight:800; color:var(--green); }
  nav a { margin-left:auto; color:var(--muted); text-decoration:none; font-size:.9rem; font-weight:600; }
  main { max-width:520px; margin:0 auto; padding:24px 16px 60px; }
  h1 { font-size:1.4rem; margin-bottom:6px; }
  .sub { color:var(--muted); margin-bottom:22px; font-size:.92rem; }
  .card { background:#fff; border-radius:14px; padding:24px; box-shadow:0 1px 4px rgba(0,0,0,.06); }
  .field { margin-bottom:18px; }
  label { display:block; font-size:.9rem; font-weight:700; margin-bottom:6px; }
  label .ic { margin-right:6px; }
  input[type=time] { width:100%; border:1.5px solid var(--border); border-radius:10px; padding:12px; font-size:1.05rem; outline:none; font-family:inherit; }
  input[type=time]:focus { border-color:var(--green); }
  .auto { background:#f7f9fc; border-radius:10px; padding:11px 13px; font-size:.84rem; color:var(--muted); margin-bottom:18px; }
  .auto b { color:var(--green); }
  button { width:100%; padding:14px; background:var(--green); color:#fff; border:none; border-radius:10px; font-size:1rem; font-weight:700; cursor:pointer; }
  button:hover:not(:disabled) { background:#0c7669; }
  button:disabled { opacity:.6; cursor:not-allowed; }
  .status { margin-top:14px; padding:12px; border-radius:10px; font-size:.9rem; display:none; }
  .ok { background:#e8f5e9; color:#2e7d32; display:block; }
  .err { background:#fdecea; color:#c62828; display:block; }
</style>
</head>
<body>
<nav>
  <span style="font-size:1.4rem">⏰</span>
  <span class="logo">MTB Nutrition</span>
  <a href="/portal/">← Voltar ao portal</a>
</nav>
<main>
  <h1>Horários das refeições</h1>
  <p class="sub">Defina quando você costuma comer. Vale para todos os dias e pode ser alterado a qualquer momento. Os cardápios usam esses horários.</p>
  <div class="card">
    <div class="field">
      <label><span class="ic">🌅</span>Café da manhã</label>
      <input type="time" id="cafe">
    </div>
    <div class="field">
      <label><span class="ic">🍽️</span>Almoço</label>
      <input type="time" id="almoco">
    </div>
    <div class="field">
      <label><span class="ic">☕</span>Lanche da tarde</label>
      <input type="time" id="lanche_tarde">
    </div>
    <div class="field">
      <label><span class="ic">🌙</span>Jantar</label>
      <input type="time" id="jantar">
    </div>
    <button id="btn" onclick="salvar()">💾 Salvar horários</button>
    <div id="st" class="status"></div>
  </div>
</main>
<script>
  const campos = ['cafe','almoco','lanche_tarde','jantar'];
  async function carregar() {
    const r = await fetch('/nutrition/horarios');
    const d = await r.json();
    campos.forEach(k => document.getElementById(k).value = d[k]);
  }
  async function salvar() {
    const btn = document.getElementById('btn'), st = document.getElementById('st');
    const body = {};
    campos.forEach(k => body[k] = document.getElementById(k).value);
    btn.disabled = true; btn.textContent = 'Salvando...'; st.className='status';
    try {
      const r = await fetch('/nutrition/horarios', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Erro');
      st.className='status ok'; st.textContent='✅ Horários salvos!';
    } catch(e) { st.className='status err'; st.textContent='❌ ' + e.message; }
    finally { btn.disabled=false; btn.textContent='💾 Salvar horários'; }
  }
  carregar();
</script>
</body>
</html>"""
