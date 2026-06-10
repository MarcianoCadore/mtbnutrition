import os
import shutil
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
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
