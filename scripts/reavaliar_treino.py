"""Reavalia treinos já sincronizados, recomputando a análise IA pós-treino e a nota.

Útil quando a lógica de análise muda (ex.: passou a considerar tempo-em-zona, o
lag fisiológico da FC e a nota de 0-10) e queremos reprocessar treinos já
sincronizados sem disparar uma nova sincronização do Garmin.

Uso (a partir da raiz do projeto, com o venv):
    python -m scripts.reavaliar_treino 2026-06-16   # uma data
    python -m scripts.reavaliar_treino all          # todos os treinos com resultado
"""
import asyncio
import json
import os
import sys

from app.services.mongo_service import get_db
from app.services.ai_service import analisar_atividade_pos_treino
from app.services.garmin_service import UPLOADS_DIR


async def _reavaliar_um(db, doc: dict, t: dict) -> None:
    semana = doc["semana_inicio"]
    user_id = doc.get("user_id")
    data = t["data"]
    resultado = t["resultado"]
    fit_file = resultado.get("fit_file")
    fit_path = os.path.join(UPLOADS_DIR, semana, fit_file) if fit_file else None
    tem_fit = bool(fit_path and os.path.exists(fit_path))

    print(f"\n=== {data} | tipo={t.get('tipo')} | user={user_id} ===")
    print(f".fit existe: {tem_fit} | FC média: {resultado.get('avg_hr')} | FC máx: {resultado.get('max_hr')}")

    nova = await analisar_atividade_pos_treino(
        t, resultado, user_id, fit_path if tem_fit else None
    )
    print(f"nota: {nova.get('nota')}")
    print(json.dumps(nova, ensure_ascii=False, indent=2))

    await db.semanas.update_one(
        {"_id": doc["_id"], "treinos.data": data},
        {"$set": {"treinos.$.resultado.analise_ia": nova}},
    )
    print("✔ salvo")


async def reavaliar(alvo: str) -> None:
    db = get_db()
    if alvo == "all":
        filtro = {"treinos": {"$elemMatch": {"resultado": {"$exists": True, "$ne": None}}}}
    else:
        filtro = {"treinos": {"$elemMatch": {"data": alvo, "resultado": {"$ne": None}}}}

    docs = [d async for d in db.semanas.find(filtro)]
    if not docs:
        print("Nenhum treino com resultado encontrado.")
        return

    total = 0
    for doc in docs:
        for t in doc.get("treinos", []):
            if not t.get("resultado"):
                continue
            if alvo != "all" and t.get("data") != alvo:
                continue
            await _reavaliar_um(db, doc, t)
            total += 1

    print(f"\n>>> {total} treino(s) reavaliado(s).")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python -m scripts.reavaliar_treino AAAA-MM-DD | all")
        sys.exit(1)
    asyncio.run(reavaliar(sys.argv[1]))
