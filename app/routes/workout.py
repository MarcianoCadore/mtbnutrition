import os
import shutil
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from app.models.models import Treino, TipoTreino
from app.services.mongo_service import get_db
from app.services.fit_service import analisar_fit
from app.services.ai_service import classificar_tipo_treino

UPLOADS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "fit")
os.makedirs(UPLOADS_DIR, exist_ok=True)

router = APIRouter()


class TreinoSemana(BaseModel):
    data: str
    tipo: TipoTreino
    periodo: Optional[str] = None   # manha | meio_dia | tarde | noite
    duracao_min: Optional[int] = None
    distancia_km: Optional[float] = None
    elevacao_m: Optional[float] = None
    cadencia_rpm: Optional[str] = None
    descricao: Optional[str] = None
    fit_file: Optional[str] = None
    garmin_workout_id: Optional[str] = None
    resultado: Optional[dict] = None


class PlanoSemanal(BaseModel):
    semana_inicio: str
    objetivo: str = ""
    treinos: list[TreinoSemana]


@router.post("/", response_model=dict)
async def criar_treino(treino: Treino):
    if treino.data is None:
        treino.data = datetime.now()
    db = get_db()
    result = await db.treinos.insert_one(treino.model_dump())
    return {"id": str(result.inserted_id), "status": "criado"}


@router.get("/")
async def listar_treinos():
    db = get_db()
    treinos = await db.treinos.find({}, {"_id": 0}).to_list(50)
    return treinos


@router.get("/hoje")
async def treino_hoje():
    db = get_db()
    hoje = datetime.now().date()
    doc = await db.treinos.find_one(
        {"data": {"$gte": datetime(hoje.year, hoje.month, hoje.day)}},
        {"_id": 0}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Nenhum treino hoje")
    return doc


@router.get("/semana/{semana_inicio}")
async def get_semana(semana_inicio: str):
    db = get_db()
    doc = await db.semanas.find_one({"semana_inicio": semana_inicio}, {"_id": 0})
    if not doc:
        return {"semana_inicio": semana_inicio, "objetivo": "", "treinos": []}
    return doc


@router.post("/semana")
async def salvar_semana(plano: PlanoSemanal):
    db = get_db()

    # preserva resultado e garmin_workout_id que vêm do sync automático
    existing = await db.semanas.find_one({"semana_inicio": plano.semana_inicio})
    data = plano.model_dump()
    if existing:
        preserve_map = {
            t["data"]: {
                "resultado": t.get("resultado"),
                "garmin_workout_id": t.get("garmin_workout_id"),
            }
            for t in existing.get("treinos", [])
        }
        for t in data["treinos"]:
            saved = preserve_map.get(t["data"], {})
            if saved.get("resultado") and not t.get("resultado"):
                t["resultado"] = saved["resultado"]
            if saved.get("garmin_workout_id") and not t.get("garmin_workout_id"):
                t["garmin_workout_id"] = saved["garmin_workout_id"]

    await db.semanas.replace_one(
        {"semana_inicio": plano.semana_inicio},
        data,
        upsert=True,
    )
    return {"status": "salvo", "semana": plano.semana_inicio}


@router.post("/garmin/sync/{semana_inicio}")
async def sync_garmin(semana_inicio: str):
    from app.services.garmin_service import sync_treinos_planejados, sync_atividades
    pl = await sync_treinos_planejados(semana_inicio)
    at = await sync_atividades(semana_inicio)
    # reclassifica a partir das descrições recém-importadas (independe da quota do Gemini)
    rc = await reclassificar_semana(semana_inicio)
    return {
        "status": "ok",
        "treinos_importados": pl,
        "atividades_processadas": at,
        "reclassificados": rc.get("reclassificados", 0),
    }


@router.post("/reclassificar/{semana_inicio}")
async def reclassificar_semana(semana_inicio: str):
    """Reclassifica o tipo de cada treino da semana a partir da descrição salva.

    Não depende do Garmin — usa o classificador determinístico por texto.
    Treinos sem descrição ou de descanso explícito não são alterados.
    """
    from app.services.ai_service import classificar_por_texto

    db = get_db()
    doc = await db.semanas.find_one({"semana_inicio": semana_inicio})
    if not doc:
        return {"status": "sem treinos", "reclassificados": 0}

    alterados = []
    for t in doc.get("treinos", []):
        descricao = t.get("descricao")
        if not descricao:
            continue
        novo_tipo = classificar_por_texto(descricao)
        if novo_tipo and novo_tipo != t.get("tipo"):
            await db.semanas.update_one(
                {"semana_inicio": semana_inicio, "treinos.data": t["data"]},
                {"$set": {"treinos.$.tipo": novo_tipo}},
            )
            alterados.append({"data": t["data"], "de": t.get("tipo"), "para": novo_tipo})

    return {"status": "ok", "reclassificados": len(alterados), "detalhes": alterados}


@router.get("/garmin/debug/{semana_inicio}")
async def debug_garmin(semana_inicio: str):
    """Retorna o raw da API Garmin para diagnóstico."""
    from datetime import timedelta
    from app.services.garmin_service import get_garmin_client
    api = get_garmin_client()
    d0 = datetime.strptime(semana_inicio, "%Y-%m-%d").date()
    d1 = d0 + timedelta(days=6)

    atividades_raw = []
    try:
        atividades_raw = api.get_activities_by_date(d0.isoformat(), d1.isoformat()) or []
    except Exception as e:
        atividades_raw = [{"erro": str(e)}]

    workouts_raw = {}
    try:
        workouts_raw = api.get_scheduled_workouts(d0.year, d0.month)
    except Exception as e:
        workouts_raw = {"erro": str(e)}

    return {
        "semana": f"{d0} a {d1}",
        "atividades_count": len(atividades_raw),
        "atividades_tipos": [
            {
                "id": a.get("activityId"),
                "nome": a.get("activityName"),
                "data": a.get("startTimeLocal", "")[:10],
                "typeKey": (a.get("activityType") or {}).get("typeKey"),
            }
            for a in atividades_raw[:10]
        ],
        "workouts_raw_type": type(workouts_raw).__name__,
        "workouts_raw_keys": list(workouts_raw.keys()) if isinstance(workouts_raw, dict) else None,
        "workouts_raw_preview": workouts_raw if isinstance(workouts_raw, dict) else workouts_raw[:3],
        "db_semana": await get_db().semanas.find_one({"semana_inicio": semana_inicio}, {"_id": 0}),
    }


@router.post("/gerar-proxima-semana/{semana_atual}")
async def gerar_proxima_semana(semana_atual: str):
    """Usa IA para gerar o plano da próxima semana com base na análise da atual."""
    from app.services.plano_semana_service import gerar_proxima_semana as _gerar
    try:
        return await _gerar(semana_atual)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


class EnviarGarminBody(BaseModel):
    semana_inicio: str
    objetivo: str = ""
    treinos: list[TreinoSemana]


@router.post("/enviar-garmin")
async def enviar_para_garmin(body: EnviarGarminBody):
    """Salva semana no DB e envia cada treino para o Garmin Connect."""
    from app.services.garmin_workout_service import upload_e_agendar

    db = get_db()
    data = {
        "semana_inicio": body.semana_inicio,
        "objetivo": body.objetivo,
        "treinos": [t.model_dump() for t in body.treinos],
    }
    await db.semanas.replace_one(
        {"semana_inicio": body.semana_inicio},
        data,
        upsert=True,
    )

    resultados = []
    for t in body.treinos:
        if t.tipo in ("DESCANSO",) or not t.duracao_min:
            resultados.append({"data": t.data, "status": "pulado"})
            continue

        nome = f"{t.tipo.replace('_', ' ')} — {t.data}"
        gid = await upload_e_agendar(
            tipo=t.tipo,
            duracao_min=t.duracao_min,
            nome=nome,
            data_iso=t.data,
            descricao=t.descricao,
        )
        if gid:
            await db.semanas.update_one(
                {"semana_inicio": body.semana_inicio, "treinos.data": t.data},
                {"$set": {"treinos.$.garmin_workout_id": gid}},
            )
        resultados.append({"data": t.data, "tipo": t.tipo, "garmin_id": gid, "status": "ok" if gid else "erro"})

    enviados = sum(1 for r in resultados if r.get("status") == "ok")
    return {"status": "ok", "semana": body.semana_inicio, "enviados": enviados, "detalhes": resultados}


@router.get("/zonas/dados")
async def ler_zonas():
    """Zonas de FC atualmente configuradas."""
    from app.services.config_service import get_zonas
    return await get_zonas()


@router.post("/zonas/extrair")
async def extrair_zonas(imagem: UploadFile = File(...)):
    """Recebe uma captura de tela do Garmin e extrai as zonas via IA (preview)."""
    if not (imagem.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="Envie um arquivo de imagem (PNG/JPG).")
    conteudo = await imagem.read()
    if len(conteudo) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Imagem muito grande (máx. 8 MB).")
    from app.services.ai_service import extrair_zonas_de_imagem
    try:
        dados = await extrair_zonas_de_imagem(conteudo, imagem.content_type)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Não consegui ler as zonas da imagem: {e}")
    return dados


class ZonaItem(BaseModel):
    zona: int
    min: int
    max: int


class ZonasBody(BaseModel):
    fc_max: Optional[int] = None
    limiar: Optional[int] = None
    zonas: list[ZonaItem]


@router.post("/zonas/salvar")
async def salvar_zonas_endpoint(body: ZonasBody):
    """Valida e salva as zonas de FC. Passam a valer nos próximos envios ao Garmin."""
    from app.services.config_service import salvar_zonas
    try:
        return await salvar_zonas(body.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/zonas", response_class=HTMLResponse)
async def pagina_zonas():
    return _PAGINA_ZONAS


@router.post("/fit/{semana_inicio}/{data}")
async def upload_fit(semana_inicio: str, data: str, arquivo: UploadFile = File(...)):
    if not arquivo.filename.lower().endswith(".fit"):
        raise HTTPException(status_code=400, detail="Apenas arquivos .fit são permitidos")

    dest_dir = os.path.join(UPLOADS_DIR, semana_inicio)
    os.makedirs(dest_dir, exist_ok=True)
    safe_name = f"{data}.fit"
    dest_path = os.path.join(dest_dir, safe_name)

    with open(dest_path, "wb") as f:
        shutil.copyfileobj(arquivo.file, f)

    analise = analisar_fit(dest_path)

    db = get_db()
    doc = await db.semanas.find_one({"semana_inicio": semana_inicio})

    # inclui descrição já salva no banco para ajudar a IA a classificar
    descricao_existente = None
    if doc:
        for t in doc.get("treinos", []):
            if t.get("data") == data:
                descricao_existente = t.get("descricao")
                break
    if descricao_existente:
        analise["descricao_existente"] = descricao_existente

    # chama IA sempre que houver qualquer dado útil
    if analise.get("descricao_estruturada") or analise.get("workout_name") or analise.get("descricao_existente") or analise.get("avg_hr"):
        analise["tipo"] = await classificar_tipo_treino(analise)

    novo_treino = {
        "data": data,
        "tipo": analise.get("tipo", "DESCANSO"),
        "duracao_min": analise.get("duracao_min"),
        "distancia_km": analise.get("distancia_km"),
        "elevacao_m": analise.get("elevacao_m"),
        "cadencia_rpm": analise.get("cadencia_rpm"),
        "fit_file": safe_name,
    }

    if not doc:
        await db.semanas.insert_one({
            "semana_inicio": semana_inicio,
            "objetivo": "",
            "treinos": [novo_treino],
        })
    else:
        treino_existe = any(t.get("data") == data for t in doc.get("treinos", []))
        if treino_existe:
            # apenas campos com valor — preserva descricao já salva
            fields = {f"treinos.$.{k}": v for k, v in novo_treino.items() if v is not None}
            await db.semanas.update_one(
                {"semana_inicio": semana_inicio, "treinos.data": data},
                {"$set": fields},
            )
        else:
            await db.semanas.update_one(
                {"semana_inicio": semana_inicio},
                {"$push": {"treinos": novo_treino}},
            )

    return {"status": "ok", "fit_file": safe_name, **analise}


@router.delete("/fit/{semana_inicio}/{data}")
async def remover_fit(semana_inicio: str, data: str):
    dest_path = os.path.join(UPLOADS_DIR, semana_inicio, f"{data}.fit")
    if os.path.exists(dest_path):
        os.remove(dest_path)
    db = get_db()
    await db.semanas.update_one(
        {"semana_inicio": semana_inicio, "treinos.data": data},
        {
            "$set":   {"treinos.$.tipo": "DESCANSO"},
            "$unset": {
                "treinos.$.fit_file":     "",
                "treinos.$.duracao_min":  "",
                "treinos.$.distancia_km": "",
                "treinos.$.elevacao_m":   "",
            },
        },
    )
    return {"status": "removido"}


@router.get("/fit/{semana_inicio}/{data}")
async def download_fit(semana_inicio: str, data: str):
    dest_path = os.path.join(UPLOADS_DIR, semana_inicio, f"{data}.fit")
    if not os.path.exists(dest_path):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    return FileResponse(dest_path, media_type="application/octet-stream", filename=f"{data}.fit")


_PAGINA_ZONAS = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MTB Nutrition — Zonas de FC</title>
<style>
  * { box-sizing:border-box; margin:0; padding:0; }
  :root { --green:#0e8a7d; --text:#1f2937; --muted:#6b7280; --border:#e5e7eb; --bg:#f0f2f5; }
  body { font-family:-apple-system,BlinkMacSystemFont,sans-serif; background:var(--bg); color:var(--text); }
  nav { background:#fff; border-bottom:1px solid var(--border); padding:14px 20px; display:flex; align-items:center; gap:10px; }
  nav .logo { font-weight:800; color:var(--green); }
  nav a { margin-left:auto; color:var(--muted); text-decoration:none; font-size:.9rem; font-weight:600; }
  main { max-width:560px; margin:0 auto; padding:24px 16px 60px; }
  h1 { font-size:1.4rem; margin-bottom:6px; }
  .sub { color:var(--muted); margin-bottom:22px; font-size:.92rem; }
  .card { background:#fff; border-radius:14px; padding:22px; box-shadow:0 1px 4px rgba(0,0,0,.06); margin-bottom:18px; }
  .card h2 { font-size:1.05rem; color:var(--green); margin-bottom:6px; }
  .card p.hint { font-size:.85rem; color:var(--muted); margin-bottom:14px; }
  .upload-row { display:flex; gap:10px; flex-wrap:wrap; align-items:center; }
  input[type=file] { flex:1; min-width:180px; font-size:.85rem; }
  .zona-row { display:grid; grid-template-columns:54px 1fr 14px 1fr; gap:10px; align-items:center; margin-bottom:12px; }
  .zona-tag { font-weight:800; color:#fff; text-align:center; border-radius:6px; padding:6px 0; font-size:.85rem; }
  .z1 { background:#9ca3af; } .z2 { background:#3b82f6; } .z3 { background:#10b981; }
  .z4 { background:#f59e0b; } .z5 { background:#ef4444; }
  .sep { text-align:center; color:var(--muted); }
  label.fld { display:block; font-size:.72rem; color:var(--muted); text-transform:uppercase; letter-spacing:.4px; margin-bottom:3px; }
  input[type=number] { width:100%; border:1.5px solid var(--border); border-radius:9px; padding:10px; font-size:1rem; outline:none; font-family:inherit; }
  input[type=number]:focus { border-color:var(--green); }
  .duo { display:flex; gap:12px; margin-top:6px; }
  .duo > div { flex:1; }
  button { width:100%; padding:14px; background:var(--green); color:#fff; border:none; border-radius:10px; font-size:1rem; font-weight:700; cursor:pointer; }
  button:hover:not(:disabled) { background:#0c7669; }
  button:disabled { opacity:.6; cursor:not-allowed; }
  button.sec { background:#374151; }
  button.sec:hover:not(:disabled) { background:#1f2937; }
  .status { margin-top:14px; padding:12px; border-radius:10px; font-size:.9rem; display:none; }
  .ok { background:#e8f5e9; color:#2e7d32; display:block; }
  .err { background:#fdecea; color:#c62828; display:block; }
  .info { background:#eef6ff; color:#1d4ed8; display:block; }
</style>
</head>
<body>
<nav>
  <span style="font-size:1.4rem">❤️</span>
  <span class="logo">MTB Nutrition</span>
  <a href="/portal/">← Voltar ao portal</a>
</nav>
<main>
  <h1>Zonas de frequência cardíaca</h1>
  <p class="sub">Configure as faixas de bpm de cada zona. Elas são enviadas como alvo nos treinos que vão para o Garmin.</p>

  <div class="card">
    <h2>📷 Ler da imagem do Garmin</h2>
    <p class="hint">Tire um print da tela de zonas de FC no app/relógio Garmin e envie aqui — a IA preenche os campos automaticamente. Confira antes de salvar.</p>
    <div class="upload-row">
      <input type="file" id="img" accept="image/*">
      <button class="sec" id="btnLer" style="width:auto; padding:12px 16px" onclick="lerImagem()">🤖 Ler zonas</button>
    </div>
    <div id="stImg" class="status"></div>
  </div>

  <div class="card">
    <h2>✏️ Zonas (bpm)</h2>
    <p class="hint">Min e max de cada zona. Você pode editar manualmente a qualquer momento.</p>
    <div id="zonas"></div>
    <div class="duo">
      <div>
        <label class="fld">FC máxima</label>
        <input type="number" id="fc_max" min="100" max="230">
      </div>
      <div>
        <label class="fld">Limiar de lactato</label>
        <input type="number" id="limiar" min="100" max="230">
      </div>
    </div>
    <div style="margin-top:18px">
      <button id="btnSalvar" onclick="salvar()">💾 Salvar zonas</button>
    </div>
    <div id="st" class="status"></div>
  </div>
</main>
<script>
  const CORES = ['z1','z2','z3','z4','z5'];
  function renderZonas(zonas) {
    const box = document.getElementById('zonas');
    box.innerHTML = '';
    for (let i = 1; i <= 5; i++) {
      const z = (zonas || []).find(x => Number(x.zona) === i) || {min:'', max:''};
      const row = document.createElement('div');
      row.className = 'zona-row';
      row.innerHTML = `
        <div class="zona-tag ${CORES[i-1]}">Z${i}</div>
        <div><label class="fld">min</label><input type="number" id="z${i}_min" min="60" max="230" value="${z.min ?? ''}"></div>
        <div class="sep">–</div>
        <div><label class="fld">max</label><input type="number" id="z${i}_max" min="60" max="230" value="${z.max ?? ''}"></div>`;
      box.appendChild(row);
    }
  }
  function coletar() {
    const zonas = [];
    for (let i = 1; i <= 5; i++) {
      zonas.push({
        zona: i,
        min: Number(document.getElementById(`z${i}_min`).value),
        max: Number(document.getElementById(`z${i}_max`).value),
      });
    }
    const fc = document.getElementById('fc_max').value;
    const lim = document.getElementById('limiar').value;
    return { fc_max: fc ? Number(fc) : null, limiar: lim ? Number(lim) : null, zonas };
  }
  function aplicar(d) {
    renderZonas(d.zonas);
    if (d.fc_max != null) document.getElementById('fc_max').value = d.fc_max;
    if (d.limiar != null) document.getElementById('limiar').value = d.limiar;
  }
  async function carregar() {
    try {
      const r = await fetch('/workout/zonas/dados');
      aplicar(await r.json());
    } catch(e) { renderZonas([]); }
  }
  async function lerImagem() {
    const inp = document.getElementById('img'), st = document.getElementById('stImg'), btn = document.getElementById('btnLer');
    if (!inp.files.length) { st.className='status err'; st.textContent='⚠️ Escolha uma imagem primeiro.'; return; }
    btn.disabled = true; btn.textContent = 'Lendo...'; st.className='status info'; st.textContent='🤖 Analisando a imagem...';
    try {
      const fd = new FormData(); fd.append('imagem', inp.files[0]);
      const r = await fetch('/workout/zonas/extrair', { method:'POST', body: fd });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Erro');
      aplicar(d);
      st.className='status ok'; st.textContent='✅ Zonas preenchidas! Confira os valores e clique em Salvar.';
    } catch(e) { st.className='status err'; st.textContent='❌ ' + e.message; }
    finally { btn.disabled=false; btn.textContent='🤖 Ler zonas'; }
  }
  async function salvar() {
    const btn = document.getElementById('btnSalvar'), st = document.getElementById('st');
    btn.disabled = true; btn.textContent = 'Salvando...'; st.className='status';
    try {
      const r = await fetch('/workout/zonas/salvar', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(coletar()) });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Erro');
      aplicar(d);
      st.className='status ok'; st.textContent='✅ Zonas salvas! Já valem para os próximos treinos enviados ao Garmin.';
    } catch(e) { st.className='status err'; st.textContent='❌ ' + e.message; }
    finally { btn.disabled=false; btn.textContent='💾 Salvar zonas'; }
  }
  carregar();
</script>
</body>
</html>"""
