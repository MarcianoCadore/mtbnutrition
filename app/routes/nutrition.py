from fastapi import APIRouter, HTTPException
from datetime import datetime
from app.models.models import PlanoAlimentar, Treino
from app.services.ai_service import gerar_plano_alimentar
from app.services.mongo_service import get_db

router = APIRouter()


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
