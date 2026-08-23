import os
import shutil
import logging
import uuid
from fastapi import APIRouter, HTTPException, UploadFile, File, Request, Form
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional
from app.models.models import Treino, TipoTreino
from app.services.mongo_service import get_db
from app.services.fit_service import analisar_fit
from app.services.ai_service import classificar_tipo_treino
from app.utils import hoje_local
from config.settings import settings

UPLOADS_DIR = settings.UPLOADS_DIR or os.path.join(
    os.path.dirname(__file__), "..", "..", "uploads", "fit"
)
os.makedirs(UPLOADS_DIR, exist_ok=True)

router = APIRouter()
logger = logging.getLogger(__name__)


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
async def criar_treino(request: Request, treino: Treino):
    if treino.data is None:
        treino.data = datetime.now()
    db = get_db()
    doc = treino.model_dump()
    doc["user_id"] = request.state.user_id
    result = await db.treinos.insert_one(doc)
    return {"id": str(result.inserted_id), "status": "criado"}


@router.get("/")
async def listar_treinos(request: Request):
    db = get_db()
    treinos = await db.treinos.find({"user_id": request.state.user_id}, {"_id": 0}).to_list(50)
    return treinos


@router.get("/hoje")
async def treino_hoje(request: Request):
    db = get_db()
    hoje = hoje_local()
    doc = await db.treinos.find_one(
        {"user_id": request.state.user_id,
         "data": {"$gte": datetime(hoje.year, hoje.month, hoje.day)}},
        {"_id": 0}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Nenhum treino hoje")
    return doc


@router.get("/semana/{semana_inicio}")
async def get_semana(request: Request, semana_inicio: str):
    from datetime import date, timedelta
    db = get_db()
    user_id = request.state.user_id
    doc = await db.semanas.find_one(
        {"semana_inicio": semana_inicio, "user_id": user_id}, {"_id": 0})

    prox = (date.fromisoformat(semana_inicio) + timedelta(days=7)).isoformat()
    # Só conta como "gerada" se veio do fluxo de IA confirmado pelo usuário — um
    # doc solto criado pelo sync do Garmin ou por um treino avulso do chat não
    # deve travar o botão de gerar a próxima semana.
    proxima_existe = await db.semanas.count_documents(
        {"semana_inicio": prox, "user_id": user_id, "gerada_por_ia": True}, limit=1)
    tem_historico = await db.semanas.count_documents(
        {"semana_inicio": {"$lt": semana_inicio}, "user_id": user_id}, limit=1)

    base = dict(doc) if doc else {"semana_inicio": semana_inicio, "objetivo": "", "treinos": []}
    # Garantia de display: título (tipo) e descrição coerentes. Limpa a descrição
    # (bpm — a FC real vem do modal/legenda — e os cabeçalhos "TIPO — DATA" que o
    # round-trip de sync acumula) e, quando a série principal da descrição é
    # inequívoca (blocos de Z5), faz o tipo SEGUIR a descrição: se o texto é de
    # VO2máx, o badge não pode ficar "Recuperação".
    from app.services.plano_semana_service import limpar_descricao_planejada
    from app.services.ai_service import tipo_definitivo
    from app.services.garmin_service import tss_planejado
    for t in base.get("treinos", []):
        if t.get("descricao"):
            t["descricao"] = limpar_descricao_planejada(t["descricao"])
            td = tipo_definitivo(t["descricao"])
            if td and td != t.get("tipo"):
                t["tipo"] = td
        t["tss_planejado"] = tss_planejado(t.get("tipo"), t.get("duracao_min"))
    base["proxima_semana_gerada"] = bool(proxima_existe)
    base["tem_historico"] = bool(tem_historico)
    return base


@router.post("/semana")
async def salvar_semana(request: Request, plano: PlanoSemanal):
    from datetime import datetime as _dt, timezone, timedelta
    db = get_db()
    user_id = request.state.user_id
    # usa horário de Brasília (UTC-3) para evitar que às 21h o servidor veja o dia seguinte
    today_iso = _dt.now(timezone(timedelta(hours=-3))).date().isoformat()

    # preserva resultado e garmin_workout_id que vêm do sync automático
    # e bloqueia edição manual de treinos presentes/futuros sem resultado (apenas IA pode sobrescrever)
    existing = await db.semanas.find_one(
        {"semana_inicio": plano.semana_inicio, "user_id": user_id})
    data = plano.model_dump()
    data["user_id"] = user_id
    if existing:
        # preserva objetivo do banco quando o request traz string vazia
        if not data.get("objetivo") and existing.get("objetivo"):
            data["objetivo"] = existing["objetivo"]
        # extras (origem="extra") são geridos por endpoints próprios e nunca
        # passam por este payload — de fora do dict de preservação (senão,
        # compartilhando data com o primário, um extra poderia "vencer" aqui
        # e ser confundido com o primário salvo) e reanexados abaixo, senão o
        # replace_one below os apagaria (collect() só manda os 7 primários).
        existing_map = {
            t["data"]: t
            for t in existing.get("treinos", [])
            if t.get("origem") != "extra"
        }
        extras_existentes = [t for t in existing.get("treinos", []) if t.get("origem") == "extra"]
        for i, t in enumerate(data["treinos"]):
            saved = existing_map.get(t["data"], {})
            # preserva resultado, garmin_workout_id e indoor do sync / toggle
            if saved.get("resultado") and not t.get("resultado"):
                t["resultado"] = saved["resultado"]
            if saved.get("garmin_workout_id") and not t.get("garmin_workout_id"):
                t["garmin_workout_id"] = saved["garmin_workout_id"]
            if saved.get("indoor") is not None and t.get("indoor") is None:
                t["indoor"] = saved["indoor"]
            # academia não está no modelo TreinoSemana → seria descartada no
            # model_dump(); preserva o bloco salvo quando o cliente não o envia.
            if saved.get("academia") and not t.get("academia"):
                t["academia"] = saved["academia"]
            # execucao (checklist da academia + sensação) é escrita só pela rota
            # /academia-execucao e também não está no modelo — sem preservar,
            # salvar a semana apagaria os checks que o atleta acabou de dar.
            if saved.get("execucao") and not t.get("execucao"):
                t["execucao"] = saved["execucao"]
            # bloqueia alteração se data >= hoje E treino ainda não foi realizado
            if t["data"] >= today_iso and not saved.get("resultado") and saved:
                data["treinos"][i] = saved
        data["treinos"].extend(extras_existentes)

    await db.semanas.replace_one(
        {"semana_inicio": plano.semana_inicio, "user_id": user_id},
        data,
        upsert=True,
    )
    return {"status": "salvo", "semana": plano.semana_inicio}


@router.post("/garmin/sync/{semana_inicio}")
async def sync_garmin(request: Request, semana_inicio: str):
    from app.services.garmin_service import sync_treinos_planejados, sync_atividades
    user_id = request.state.user_id
    pl = await sync_treinos_planejados(user_id, semana_inicio)
    at = await sync_atividades(user_id, semana_inicio)
    # reclassifica a partir das descrições recém-importadas (independe da quota do Gemini)
    rc = await _reclassificar_impl(user_id, semana_inicio)
    return {
        "status": "ok",
        "treinos_importados": pl,
        "atividades_processadas": at,
        "reclassificados": rc.get("reclassificados", 0),
    }


async def _reclassificar_impl(user_id: str, semana_inicio: str) -> dict:
    """Reclassifica o tipo de cada treino da semana a partir da descrição salva."""
    from app.services.ai_service import classificar_por_texto

    db = get_db()
    doc = await db.semanas.find_one({"semana_inicio": semana_inicio, "user_id": user_id})
    if not doc:
        return {"status": "sem treinos", "reclassificados": 0}

    alterados = []
    for t in doc.get("treinos", []):
        if t.get("origem") == "extra":
            continue  # reclassificação é fluxo automático só do primário
        descricao = t.get("descricao")
        if not descricao:
            continue
        novo_tipo = classificar_por_texto(descricao)
        if novo_tipo and novo_tipo != t.get("tipo"):
            await db.semanas.update_one(
                {
                    "semana_inicio": semana_inicio, "user_id": user_id,
                    "treinos": {"$elemMatch": {"data": t["data"], "origem": {"$ne": "extra"}}},
                },
                {"$set": {"treinos.$.tipo": novo_tipo}},
            )
            alterados.append({"data": t["data"], "de": t.get("tipo"), "para": novo_tipo})

    return {"status": "ok", "reclassificados": len(alterados), "detalhes": alterados}


@router.post("/reclassificar/{semana_inicio}")
async def reclassificar_semana(request: Request, semana_inicio: str):
    """Reclassifica o tipo de cada treino da semana a partir da descrição salva.

    Não depende do Garmin — usa o classificador determinístico por texto.
    Treinos sem descrição ou de descanso explícito não são alterados.
    """
    return await _reclassificar_impl(request.state.user_id, semana_inicio)


@router.get("/garmin/debug/{semana_inicio}")
async def debug_garmin(request: Request, semana_inicio: str):
    """Retorna o raw da API Garmin para diagnóstico."""
    from datetime import timedelta
    from app.services.garmin_service import get_garmin_client
    user_id = request.state.user_id
    try:
        api = await get_garmin_client(user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
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
        "db_semana": await get_db().semanas.find_one(
            {"semana_inicio": semana_inicio, "user_id": request.state.user_id}, {"_id": 0}),
    }


@router.post("/gerar-proxima-semana/{semana_atual}")
async def gerar_proxima_semana(request: Request, semana_atual: str):
    """Usa IA para gerar o plano da próxima semana com base na análise da atual."""
    from app.services.plano_semana_service import gerar_proxima_semana as _gerar
    try:
        return await _gerar(request.state.user_id, semana_atual)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/gerar-primeira-semana/{semana_inicio}")
async def gerar_primeira_semana(request: Request, semana_inicio: str):
    """Monta a 1ª semana de um atleta sem histórico (a partir do perfil) e SALVA.

    Marca a semana com origem='auto' para que o usuário possa apagá-la depois
    caso se arrependa (enquanto não houver nenhum treino já realizado)."""
    from app.services.plano_semana_service import gerar_primeira_semana as _gerar

    db = get_db()
    user_id = request.state.user_id

    # Não sobrescreve uma semana que já tem treino real registrado (extras não
    # contam — um extra sozinho não deve bloquear nem ser apagado por isto).
    existing = await db.semanas.find_one(
        {"semana_inicio": semana_inicio, "user_id": user_id})
    if existing and any(
        ((t.get("tipo") != "DESCANSO" and t.get("duracao_min")) or t.get("resultado"))
        and t.get("origem") != "extra"
        for t in existing.get("treinos", [])
    ):
        raise HTTPException(
            status_code=409,
            detail="Esta semana já tem treinos. Apague-os antes de gerar de novo.")

    extras_existentes = [
        t for t in (existing or {}).get("treinos", []) if t.get("origem") == "extra"
    ]
    plano = await _gerar(user_id, semana_inicio)
    doc = {
        "semana_inicio": semana_inicio,
        "user_id": user_id,
        "objetivo": plano.get("progressao", ""),
        "origem": "auto",
        "treinos": plano["treinos"] + extras_existentes,
    }
    await db.semanas.replace_one(
        {"semana_inicio": semana_inicio, "user_id": user_id}, doc, upsert=True)
    return plano


@router.delete("/primeira-semana/{semana_inicio}")
async def apagar_primeira_semana(request: Request, semana_inicio: str):
    """Apaga uma semana gerada automaticamente (undo), desde que nenhum treino
    já tenha sido realizado (resultado) — não deixa apagar histórico real."""
    db = get_db()
    user_id = request.state.user_id
    doc = await db.semanas.find_one(
        {"semana_inicio": semana_inicio, "user_id": user_id})
    if not doc:
        return {"status": "vazio"}
    if any(t.get("resultado") for t in doc.get("treinos", [])):
        raise HTTPException(
            status_code=409,
            detail="Já há treino realizado nesta semana — não dá para apagar tudo.")
    if any(t.get("origem") == "extra" for t in doc.get("treinos", [])):
        raise HTTPException(
            status_code=409,
            detail="Há um treino extra cadastrado nesta semana — remova-o antes de apagar tudo.")
    await db.semanas.delete_one({"semana_inicio": semana_inicio, "user_id": user_id})
    return {"status": "apagado", "semana": semana_inicio}


class EnviarGarminBody(BaseModel):
    semana_inicio: str
    objetivo: str = ""
    treinos: list[TreinoSemana]


@router.post("/enviar-garmin")
async def enviar_para_garmin(request: Request, body: EnviarGarminBody):
    """Salva semana no DB e envia cada treino para o Garmin Connect.

    Deleta workouts antigos do Garmin antes de enviar os novos,
    evitando duplicatas no calendário.
    """
    from app.services.garmin_workout_service import upload_e_agendar, deletar_workout_garmin

    db = get_db()
    user_id = request.state.user_id

    # Coleta garmin_workout_ids existentes para deletar antes do re-envio
    existing = await db.semanas.find_one(
        {"semana_inicio": body.semana_inicio, "user_id": user_id})
    existing_gids: dict[str, str] = {}
    extras_existentes = []
    if existing:
        for t in existing.get("treinos", []):
            if t.get("origem") == "extra":
                extras_existentes.append(t)
                continue
            if t.get("garmin_workout_id"):
                existing_gids[t["data"]] = t["garmin_workout_id"]

    objetivo = body.objetivo or (existing.get("objetivo") if existing else "") or ""
    data = {
        "semana_inicio": body.semana_inicio,
        "user_id": user_id,
        "objetivo": objetivo,
        # body.treinos são sempre primários (o plano da IA); reanexa extras
        # existentes, senão este replace_one os apagaria.
        "treinos": [t.model_dump() for t in body.treinos] + extras_existentes,
        # Marca que esta semana foi de fato confirmada pelo fluxo de IA — distingue
        # de um documento que só existe porque o sync do Garmin (ou um treino avulso
        # criado pelo chat) gravou uma entrada solta para a semana. Sem isso,
        # "próxima semana já gerada" contava qualquer doc existente e travava o
        # botão pra sempre.
        "gerada_por_ia": True,
    }
    await db.semanas.replace_one(
        {"semana_inicio": body.semana_inicio, "user_id": user_id},
        data,
        upsert=True,
    )

    resultados = []
    for t in body.treinos:
        if t.tipo in ("DESCANSO", "ACADEMIA") or not t.duracao_min:
            resultados.append({"data": t.data, "status": "pulado"})
            continue

        # Remove agendamento antigo do Garmin (se houver) — evita duplicatas
        gid_antigo = existing_gids.get(t.data)
        if gid_antigo:
            await deletar_workout_garmin(user_id, gid_antigo)

        nome = f"{t.tipo.replace('_', ' ')} — {t.data}"
        gid = await upload_e_agendar(
            user_id,
            tipo=t.tipo,
            duracao_min=t.duracao_min,
            nome=nome,
            data_iso=t.data,
            descricao=t.descricao,
        )
        if gid:
            await db.semanas.update_one(
                {
                    "semana_inicio": body.semana_inicio, "user_id": user_id,
                    "treinos": {"$elemMatch": {"data": t.data, "origem": {"$ne": "extra"}}},
                },
                {"$set": {"treinos.$.garmin_workout_id": gid}},
            )
        resultados.append({"data": t.data, "tipo": t.tipo, "garmin_id": gid, "status": "ok" if gid else "erro"})

    enviados = sum(1 for r in resultados if r.get("status") == "ok")

    # Avisa no WhatsApp com o resumo dos treinos da semana — no telefone do usuário.
    whatsapp_ok = False
    try:
        from app.services.whatsapp_service import send_semana_treinos
        from app.services.user_service import get_por_id
        user = await get_por_id(user_id)
        telefone = (user or {}).get("telefone")
        if telefone and (user or {}).get("whatsapp", {}).get("ativo"):
            await send_semana_treinos(body.semana_inicio, [t.model_dump() for t in body.treinos], to=telefone)
            whatsapp_ok = True
    except Exception as e:
        logger.error("Falha ao enviar treinos da semana no WhatsApp: %s", e)

    return {"status": "ok", "semana": body.semana_inicio, "enviados": enviados,
            "whatsapp": whatsapp_ok, "detalhes": resultados}


@router.post("/reenviar-garmin/{semana_inicio}")
async def reenviar_para_garmin(request: Request, semana_inicio: str):
    """Lê os treinos da semana do DB e re-envia ao Garmin Connect.

    Útil quando o envio original falhou silenciosamente ou o calendário do
    Garmin foi apagado. Não depende da IA — usa os dados já salvos no banco.
    """
    from app.services.garmin_workout_service import upload_e_agendar, deletar_workout_garmin

    db = get_db()
    user_id = request.state.user_id

    doc = await db.semanas.find_one({"semana_inicio": semana_inicio, "user_id": user_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Semana não encontrada no banco.")

    resultados = []
    for t in doc.get("treinos", []):
        if t.get("origem") == "extra":
            continue  # extra nunca sincroniza com o Garmin
        if t.get("tipo") in ("DESCANSO", "ACADEMIA") or not t.get("duracao_min"):
            # O dia virou descanso/academia. Se ainda houver um workout agendado
            # no Garmin, remove-o — senão o pull seguinte (sync_treinos_planejados)
            # o re-importa e o treino "volta" mesmo após ter sido excluído.
            gid_orfao = t.get("garmin_workout_id")
            if gid_orfao:
                await deletar_workout_garmin(user_id, gid_orfao)
                await db.semanas.update_one(
                    {
                        "semana_inicio": semana_inicio, "user_id": user_id,
                        "treinos": {"$elemMatch": {"data": t["data"], "origem": {"$ne": "extra"}}},
                    },
                    {"$unset": {"treinos.$.garmin_workout_id": ""}},
                )
                resultados.append({"data": t.get("data"), "status": "removido_do_garmin"})
            else:
                resultados.append({"data": t.get("data"), "status": "pulado"})
            continue

        # Remove o agendamento anterior do Garmin antes de re-enviar
        gid_antigo = t.get("garmin_workout_id")
        if gid_antigo:
            await deletar_workout_garmin(user_id, gid_antigo)

        nome = f"{t.get('tipo','').replace('_', ' ')} — {t.get('data','')}"
        gid = await upload_e_agendar(
            user_id,
            tipo=t["tipo"],
            duracao_min=t["duracao_min"],
            nome=nome,
            data_iso=t["data"],
            descricao=t.get("descricao"),
        )
        if gid:
            await db.semanas.update_one(
                {
                    "semana_inicio": semana_inicio, "user_id": user_id,
                    "treinos": {"$elemMatch": {"data": t["data"], "origem": {"$ne": "extra"}}},
                },
                {"$set": {"treinos.$.garmin_workout_id": gid}},
            )
        resultados.append({
            "data": t.get("data"),
            "tipo": t.get("tipo"),
            "garmin_id": gid,
            "status": "ok" if gid else "erro",
        })

    enviados = sum(1 for r in resultados if r.get("status") == "ok")
    return {"status": "ok", "semana": semana_inicio, "enviados": enviados, "detalhes": resultados}


@router.get("/zonas/dados")
async def ler_zonas(request: Request):
    """Zonas de FC + FTP/modo de potência atualmente configurados."""
    from app.services.config_service import get_zonas, get_zonas_potencia
    zonas_fc = await get_zonas(request.state.user_id)
    zonas_pot = await get_zonas_potencia(request.state.user_id)
    return {**zonas_fc, "potencia": zonas_pot}


@router.post("/zonas/importar-garmin")
async def importar_zonas_garmin(request: Request):
    """Lê as zonas de FC oficiais direto da conta Garmin (preview, não salva)."""
    from app.services.garmin_service import zonas_do_garmin
    user_id = request.state.user_id
    try:
        return await zonas_do_garmin(user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Não consegui ler as zonas do Garmin: {e}")


@router.post("/zonas/extrair")
async def extrair_zonas(imagem: UploadFile = File(...)):
    """Recebe uma captura de tela do Garmin e extrai as zonas via IA (preview)."""
    if not (imagem.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="Envie um arquivo de imagem (PNG/JPG).")
    conteudo = await imagem.read()
    if len(conteudo) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Imagem muito grande (máx. 8 MB).")
    from app.services.ai_service import extrair_zonas_de_imagem, QuotaExcedida, _e_cota
    try:
        dados = await extrair_zonas_de_imagem(conteudo, imagem.content_type)
    except QuotaExcedida:
        raise HTTPException(
            status_code=429,
            detail="Cota diária gratuita da IA esgotada. Preencha as zonas manualmente abaixo "
                   "ou tente a leitura por imagem novamente mais tarde.",
        )
    except Exception as e:
        if _e_cota(e):
            raise HTTPException(
                status_code=429,
                detail="Cota da IA atingida no momento. Aguarde alguns segundos e tente de novo, "
                       "ou preencha as zonas manualmente abaixo.",
            )
        raise HTTPException(status_code=422, detail=f"Não consegui ler as zonas da imagem: {e}")
    return dados


@router.post("/zonas/extrair-potencia")
async def extrair_zonas_potencia(imagem: UploadFile = File(...)):
    """Recebe captura de tela das zonas de potência do Garmin e extrai FTP + 7 zonas via IA."""
    if not (imagem.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="Envie um arquivo de imagem (PNG/JPG).")
    conteudo = await imagem.read()
    if len(conteudo) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Imagem muito grande (máx. 8 MB).")
    from app.services.ai_service import extrair_zonas_potencia_de_imagem, QuotaExcedida, _e_cota
    try:
        dados = await extrair_zonas_potencia_de_imagem(conteudo, imagem.content_type)
    except QuotaExcedida:
        raise HTTPException(
            status_code=429,
            detail="Cota diária gratuita da IA esgotada. Preencha o FTP manualmente ou tente mais tarde.",
        )
    except Exception as e:
        if _e_cota(e):
            raise HTTPException(
                status_code=429,
                detail="Cota da IA atingida. Aguarde alguns segundos e tente de novo.",
            )
        raise HTTPException(status_code=422, detail=f"Não consegui ler as zonas da imagem: {e}")
    return dados


class ZonaItem(BaseModel):
    zona: int
    min: int
    max: int


class ZonasBody(BaseModel):
    fc_max: Optional[int] = None
    limiar: Optional[int] = None
    metodo: str = "fcmax"
    zonas: list[ZonaItem]


@router.post("/zonas/salvar")
async def salvar_zonas_endpoint(request: Request, body: ZonasBody):
    """Valida e salva as zonas de FC. Após salvar, sincroniza automaticamente
    com o Garmin (todos os perfis) — best-effort, não quebra o salvamento."""
    from app.services.config_service import salvar_zonas
    try:
        salvo = await salvar_zonas(request.state.user_id, body.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    garmin = {"ok": False, "status": None}
    try:
        from app.services.garmin_service import enviar_zonas_para_garmin
        garmin = await enviar_zonas_para_garmin(request.state.user_id, salvo)
    except ValueError:
        # Usuário sem Garmin conectado — não é erro, apenas não sincroniza
        pass
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("Auto-sync de zonas com Garmin falhou: %s", e)

    salvo["garmin_sync"] = garmin
    return salvo


class FTPBody(BaseModel):
    ftp: int
    modo: str = "indoor"  # "indoor" | "sempre" | "ambos" | "nunca"


@router.post("/zonas/ftp")
async def salvar_ftp_endpoint(request: Request, body: FTPBody):
    """Salva o FTP e o modo de uso de potência. Recalcula as 7 zonas automaticamente."""
    from app.services.config_service import salvar_ftp
    try:
        return await salvar_ftp(request.state.user_id, body.ftp, body.modo)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/zonas/potencia")
async def ler_zonas_potencia(request: Request):
    """FTP e 7 zonas de potência do usuário. Retorna null se FTP não configurado."""
    from app.services.config_service import get_zonas_potencia
    return await get_zonas_potencia(request.state.user_id)


@router.get("/estrutura/{tipo}")
async def estrutura_treino(request: Request, tipo: str, duracao_min: int = 60, indoor: bool = False):
    """Segmentos (aquecimento/intervalo/recuperação/volta à calma) do treino, para
    desenhar o gráfico de estrutura no portal — mesma fonte usada para montar o
    workout enviado ao Garmin. `indoor=true` traz a faixa em watts, senão em bpm."""
    from app.services.garmin_workout_service import preview_estrutura
    from app.services.config_service import zonas_bpm_map, zonas_watts_map

    user_id = request.state.user_id
    zonas_bpm = await zonas_bpm_map(user_id)
    zonas_watts = await zonas_watts_map(user_id) if indoor else None
    dados = preview_estrutura(tipo, duracao_min, zonas_bpm, zonas_watts)
    if dados is None:
        raise HTTPException(status_code=404, detail=f"Tipo de treino sem estrutura: {tipo}")
    return dados


def _resposta_download(xml: str, nome: str, ext: str) -> Response:
    """Empacota o XML como download com a extensão dada (.xml, .zwo)."""
    import re
    slug = re.sub(r"[^a-z0-9]+", "_", nome.lower()).strip("_") or "treino"
    return Response(
        content=xml,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{slug}.{ext}"'},
    )


async def _zonas_watts_ou_erro(user_id: str) -> dict:
    """Zonas de potência do atleta ou 400 pedindo o FTP (o ERG é em watts)."""
    from app.services.config_service import zonas_watts_map
    zonas_watts = await zonas_watts_map(user_id)
    if not zonas_watts:
        raise HTTPException(
            status_code=400,
            detail="Configure seu FTP para exportar o treino ERG (as potências saem em watts).",
        )
    return zonas_watts


async def _treino_do_dia(user_id: str, semana_inicio: str, data: str) -> dict:
    """Treino principal (origem != extra) agendado numa data. 404 se não houver."""
    db = get_db()
    doc = await db.semanas.find_one({"semana_inicio": semana_inicio, "user_id": user_id})
    treino = next(
        (t for t in (doc or {}).get("treinos", []) if t["data"] == data and t.get("origem") != "extra"),
        None,
    ) if doc else None
    if not treino or treino.get("tipo") == "DESCANSO":
        raise HTTPException(status_code=404, detail="Treino não encontrado para esta data.")
    return treino


# ── ERG/XML (formato próprio: eventos desacoplados dos blocos; watts absolutos) ──

@router.get("/erg/{tipo}")
async def erg_treino(request: Request, tipo: str, duracao_min: int = 60, nome: str | None = None):
    """Exporta o treino `tipo`/`duracao_min` no formato ERG/XML (blocos de potência
    + eventos de antecipação desacoplados) para software de home trainer. Watts das
    zonas do atleta — exige FTP configurado."""
    from app.services.erg_service import build_erg_xml
    from app.services.config_service import get_ftp

    user_id = request.state.user_id
    zonas_watts = await _zonas_watts_ou_erro(user_id)
    ftp, _ = await get_ftp(user_id)
    xml = build_erg_xml(tipo, duracao_min, zonas_watts=zonas_watts, nome=nome, ftp=ftp)
    if xml is None:
        raise HTTPException(status_code=404, detail=f"Tipo de treino sem estrutura: {tipo}")
    return _resposta_download(xml, nome or tipo, "xml")


@router.get("/erg/semana/{semana_inicio}/{data}")
async def erg_treino_agendado(request: Request, semana_inicio: str, data: str):
    """ERG/XML do treino agendado numa data (usa tipo/nome/duração/descrição reais
    do dia). Exige FTP configurado."""
    from app.services.erg_service import build_erg_xml
    from app.services.config_service import get_ftp

    user_id = request.state.user_id
    zonas_watts = await _zonas_watts_ou_erro(user_id)
    treino = await _treino_do_dia(user_id, semana_inicio, data)

    ftp, _ = await get_ftp(user_id)
    xml = build_erg_xml(
        treino["tipo"],
        treino.get("duracao_min") or 60,
        zonas_watts=zonas_watts,
        nome=treino.get("nome") or treino["tipo"],
        descricao=treino.get("descricao"),
        ftp=ftp,
    )
    if xml is None:
        raise HTTPException(status_code=404, detail=f"Tipo de treino sem estrutura: {treino['tipo']}")
    return _resposta_download(xml, treino.get("nome") or treino["tipo"], "xml")


# ── .zwo (Zwift Workout): padrão dos apps de trainer. Potência RELATIVA ao FTP,
#    então NÃO exige FTP salvo — cada usuário baixa o seu próprio arquivo. ────────

def _zwo_do_treino(treino: dict) -> str | None:
    """Gera o .zwo a partir de um dict de treino (tipo/nome/descrição)."""
    from app.services.zwo_service import build_zwo_xml
    return build_zwo_xml(
        treino["tipo"],
        treino.get("duracao_min") or 60,
        nome=treino.get("nome") or treino["tipo"],
        descricao=treino.get("descricao"),
    )


@router.get("/zwo/{tipo}")
async def zwo_treino(request: Request, tipo: str, duracao_min: int = 60, nome: str | None = None):
    """Exporta o treino `tipo`/`duracao_min` em .zwo (Zwift Workout). Potência em
    fração do FTP — funciona para qualquer atleta, com ou sem FTP configurado."""
    from app.services.zwo_service import build_zwo_xml

    xml = build_zwo_xml(tipo, duracao_min, nome=nome)
    if xml is None:
        raise HTTPException(status_code=404, detail=f"Tipo de treino sem estrutura: {tipo}")
    return _resposta_download(xml, nome or tipo, "zwo")


@router.get("/zwo/semana/{semana_inicio}/{data}")
async def zwo_treino_agendado(request: Request, semana_inicio: str, data: str):
    """.zwo do treino agendado numa data (tipo/nome/duração/descrição/cadência reais
    do dia), escopado ao usuário autenticado — cada um baixa o seu próprio arquivo."""
    treino = await _treino_do_dia(request.state.user_id, semana_inicio, data)
    xml = _zwo_do_treino(treino)
    if xml is None:
        raise HTTPException(status_code=404, detail=f"Tipo de treino sem estrutura: {treino['tipo']}")
    return _resposta_download(xml, treino.get("nome") or treino["tipo"], "zwo")


# ── Execução da academia (checklist + sensação) ──────────────────────────────
# Musculação não gera atividade para o Garmin sincronizar, então quem "mede" a
# sessão é o próprio atleta: marca os exercícios conforme executa e, no fim, dá
# uma nota de 1 a 5 para como se sentiu. Dar a nota é o que finaliza a sessão —
# não existe botão de "registrar", o check-off É o registro.

SENSACAO_LABEL = {
    1: "muito ruim", 2: "ruim", 3: "normal", 4: "bem", 5: "muito bem",
}


CARGA_MAX_KG = 500.0  # acima disso é digitação errada, não levantamento


class AcademiaExecucaoBody(BaseModel):
    itens_feitos: list[int] = []
    cargas: dict[str, float] = {}   # índice do exercício (str) → kg usados
    sensacao: Optional[int] = None  # 1 (muito ruim) a 5 (muito bem)


def _fmt_kg(v: float) -> str:
    """20.0 → '20 kg'; 22.5 → '22,5 kg'."""
    return (f"{v:.0f}" if float(v).is_integer() else f"{v:.1f}".replace(".", ",")) + " kg"


def _relato_academia(exercicios: list[str], feitos: list[int],
                     cargas: dict[int, float], sensacao: Optional[int]) -> str:
    """Monta, a partir do checklist, o relato que vai para a análise da sessão.

    A carga registrada entra aqui e no `execucao` — é ela que dá à IA um número
    real para progredir, em vez de um chute sobre quanto o atleta aguenta.
    """
    def _com_carga(i: int, nome: str) -> str:
        kg = cargas.get(i)
        return f"{nome} ({_fmt_kg(kg)})" if kg else nome

    ok = [_com_carga(i, e) for i, e in enumerate(exercicios) if i in feitos]
    faltou = [e for i, e in enumerate(exercicios) if i not in feitos]
    partes = [f"Academia: {len(ok)} de {len(exercicios)} exercícios concluídos."]
    if ok:
        partes.append("Executados: " + "; ".join(ok) + ".")
    if faltou:
        partes.append("Não executados: " + "; ".join(faltou) + ".")
    if sensacao:
        partes.append(
            f"Sensação relatada pelo atleta: {sensacao}/5 "
            f"({SENSACAO_LABEL.get(sensacao, '')})."
        )
    return " ".join(partes)


@router.post("/treino/{semana_inicio}/{data}/academia-execucao")
async def academia_execucao(
    request: Request,
    semana_inicio: str,
    data: str,
    body: AcademiaExecucaoBody,
):
    """Salva o progresso do checklist e, quando vem `sensacao`, fecha a sessão.

    O corpo carrega o estado completo (não um delta), então marcar/desmarcar em
    sequência rápida não gera corrida: a última requisição vence.
    """
    from app.services.plano_semana_service import extrair_exercicios_academia
    from app.services.avaliacao_service import registrar_realizado

    db = get_db()
    user_id = request.state.user_id

    doc = await db.semanas.find_one({"semana_inicio": semana_inicio, "user_id": user_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Semana não encontrada.")

    treino = next(
        (t for t in doc.get("treinos", []) if t["data"] == data and t.get("origem") != "extra"),
        None,
    )
    if not treino:
        raise HTTPException(status_code=404, detail="Treino não encontrado para esta data.")
    # Dois lugares podem ter academia no mesmo dia:
    #  - dia SÓ de academia   → tipo=ACADEMIA, exercícios em `descricao`;
    #  - DIA DUPLO (bike+gym) → exercícios no sub-objeto `academia`.
    # No dia duplo o `resultado` do treino pertence ao PEDAL, então a execução
    # da musculação é gravada dentro do próprio sub-objeto.
    sub = treino.get("academia") or {}
    e_dia_duplo = treino.get("tipo") != "ACADEMIA" and bool(sub.get("descricao"))
    if treino.get("tipo") != "ACADEMIA" and not e_dia_duplo:
        raise HTTPException(
            status_code=400,
            detail="O checklist de execução só existe para treino de academia.",
        )
    if data > hoje_local().isoformat():
        raise HTTPException(
            status_code=400,
            detail="Este treino ainda não aconteceu — o checklist abre no dia.",
        )

    fonte = sub if e_dia_duplo else treino
    exercicios = extrair_exercicios_academia(fonte.get("descricao"))
    if not exercicios:
        raise HTTPException(
            status_code=400,
            detail="A descrição deste dia não tem lista de exercícios para marcar.",
        )

    feitos = sorted({i for i in body.itens_feitos if 0 <= i < len(exercicios)})
    if body.sensacao is not None and body.sensacao not in SENSACAO_LABEL:
        raise HTTPException(status_code=400, detail="Sensação deve ser de 1 a 5.")

    # Cargas: só índices que existem na lista e valores plausíveis. Zero/negativo
    # é "não informado" (o campo em branco), não um levantamento de 0 kg.
    cargas: dict[int, float] = {}
    for chave, valor in (body.cargas or {}).items():
        try:
            idx, kg = int(chave), float(valor)
        except (TypeError, ValueError):
            continue
        if not (0 <= idx < len(exercicios)) or kg <= 0:
            continue
        if kg > CARGA_MAX_KG:
            raise HTTPException(
                status_code=400,
                detail=f"Carga de {kg:.0f} kg parece erro de digitação.",
            )
        cargas[idx] = round(kg, 1)

    execucao = {
        "itens_feitos": feitos,
        "total_itens": len(exercicios),
        "cargas": {str(i): kg for i, kg in sorted(cargas.items())},
        "sensacao": body.sensacao,
        "atualizado_em": datetime.now(timezone.utc).isoformat(),
    }
    campo = "treinos.$.academia.execucao" if e_dia_duplo else "treinos.$.execucao"
    await db.semanas.update_one(
        {
            "semana_inicio": semana_inicio, "user_id": user_id,
            "treinos": {"$elemMatch": {"data": data, "origem": {"$ne": "extra"}}},
        },
        {"$set": {campo: execucao}},
    )

    # A sensação é o "enviar": só nela a sessão vira realizada e ganha análise.
    # No dia duplo não há `registrar_realizado`: aquele slot é do pedal, que
    # ainda vai chegar pelo Garmin. A execução da musculação fica guardada no
    # sub-objeto e é dela que sai a progressão de carga.
    registrado, nota, erro = False, None, None
    if body.sensacao is not None and not e_dia_duplo:
        try:
            r = await registrar_realizado(
                user_id, data,
                duracao_min=treino.get("duracao_min"),
                relato=_relato_academia(exercicios, feitos, cargas, body.sensacao),
                percepcao_esforco=None,
            )
            registrado, nota = True, r.get("nota")
        except ValueError as exc:
            # Ex.: sessão já sincronizada de dispositivo. O checklist fica salvo.
            erro = str(exc)
            logger.warning("academia_execucao: registro recusado em %s: %s", data, exc)

    return {
        "execucao": execucao,
        "registrado": registrado,
        "nota": nota,
        "erro": erro,
        "dia_duplo": e_dia_duplo,
    }


class IndoorBody(BaseModel):
    indoor: bool  # True = indoor (watts), False = outdoor (FC)


@router.post("/treino/{semana_inicio}/{data}/indoor")
async def marcar_indoor(
    request: Request,
    semana_inicio: str,
    data: str,
    body: IndoorBody,
):
    """Marca um treino como indoor (watts) ou outdoor (FC) e re-sincroniza com Garmin."""
    from app.services.config_service import get_zonas_potencia
    from app.services.garmin_workout_service import upload_e_agendar, deletar_workout_garmin

    db = get_db()
    user_id = request.state.user_id

    doc = await db.semanas.find_one({"semana_inicio": semana_inicio, "user_id": user_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Semana não encontrada.")

    treino = next(
        (t for t in doc.get("treinos", []) if t["data"] == data and t.get("origem") != "extra"),
        None,
    )
    if not treino or treino.get("tipo") == "DESCANSO":
        raise HTTPException(status_code=404, detail="Treino não encontrado para esta data.")

    # Academia não é treino de bike: não tem alvo de FC/watts nem builder de
    # workout no Garmin. Sem esta guarda o toggle marcava `indoor` num dia de
    # musculação e ainda tentava subir um workout de ciclismo.
    if treino.get("tipo") == "ACADEMIA":
        raise HTTPException(
            status_code=400,
            detail="Treino de academia não tem alvo de FC/watts — indoor/outdoor não se aplica.",
        )

    # Atualiza campo indoor no banco
    await db.semanas.update_one(
        {
            "semana_inicio": semana_inicio, "user_id": user_id,
            "treinos": {"$elemMatch": {"data": data, "origem": {"$ne": "extra"}}},
        },
        {"$set": {"treinos.$.indoor": body.indoor}},
    )

    garmin_sync = None
    zp = await get_zonas_potencia(user_id)
    if zp:
        # Deleta o workout antigo do Garmin (se existir)
        gid_antigo = treino.get("garmin_workout_id")
        if gid_antigo:
            await deletar_workout_garmin(user_id, gid_antigo)

        # Re-envia com o alvo correto (forcar_indoor=True/False)
        novo_gid = None
        try:
            novo_gid = await upload_e_agendar(
                user_id=user_id,
                tipo=treino["tipo"],
                duracao_min=treino.get("duracao_min") or 60,
                nome=treino.get("nome") or treino["tipo"],
                data_iso=data,
                descricao=treino.get("descricao"),
                forcar_indoor=body.indoor,
            )
            if novo_gid:
                await db.semanas.update_one(
                    {
                        "semana_inicio": semana_inicio, "user_id": user_id,
                        "treinos": {"$elemMatch": {"data": data, "origem": {"$ne": "extra"}}},
                    },
                    {"$set": {"treinos.$.garmin_workout_id": novo_gid}},
                )
                garmin_sync = {"ok": True, "gid": novo_gid}
            else:
                garmin_sync = {"ok": False, "motivo": "upload retornou vazio"}
        except Exception as e:
            garmin_sync = {"ok": False, "motivo": str(e)}

        # O antigo já foi deletado do Garmin lá em cima. Se o novo não subiu, o
        # id no banco aponta para um workout que não existe mais — limpa, senão
        # o próximo toggle tenta deletar um fantasma e o card mostra "enviado".
        if not novo_gid and gid_antigo:
            await db.semanas.update_one(
                {
                    "semana_inicio": semana_inicio, "user_id": user_id,
                    "treinos": {"$elemMatch": {"data": data, "origem": {"$ne": "extra"}}},
                },
                {"$set": {"treinos.$.garmin_workout_id": None}},
            )

    return {
        "indoor": body.indoor,
        "data": data,
        "garmin_sync": garmin_sync,
    }


class CriarFTPBody(BaseModel):
    data: str           # YYYY-MM-DD
    duracao_min: int = 62
    forcar_indoor: Optional[bool] = None


@router.post("/criar-ftp")
async def criar_treino_ftp(request: Request, body: CriarFTPBody):
    """Cria (ou recria) o treino TESTE_FTP no Garmin para a data informada.

    Busca qualquer workout já agendado nessa data, remove e faz upload do protocolo
    correto de FTP (10min Z1 → 5min Z3 → 3x aceleração → 2min Z1 → 20min FTP → 15min Z1).
    Salva referência na semana do banco (upsert).
    """
    from app.services.garmin_workout_service import upload_e_agendar

    user_id = request.state.user_id
    data_iso = body.data

    try:
        datetime.strptime(data_iso, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="data deve ser YYYY-MM-DD")

    # O cleanup de workouts existentes na data é feito dentro de upload_e_agendar.

    descricao = (
        "TESTE FTP (20min): esforço máximo sustentável. "
        "Potência média dos 20min × 0.95 = novo FTP. Não exploda no início! "
        "Aquecimento: 10min Z1 → 5min Z3 progressivo → 3×(30s Z5 + 1min Z1) → 2min Z1. "
        "Desaquecimento: 15min Z1."
    )
    nome = f"TESTE FTP — {data_iso}"
    gid = await upload_e_agendar(
        user_id=user_id,
        tipo="TESTE_FTP",
        duracao_min=body.duracao_min,
        nome=nome,
        data_iso=data_iso,
        descricao=descricao,
        forcar_indoor=body.forcar_indoor,
    )

    if not gid:
        raise HTTPException(status_code=502, detail="Falha ao fazer upload para o Garmin.")

    # Salva na semana do banco (upsert na semana que contém a data)
    from datetime import date, timedelta
    db = get_db()
    d = date.fromisoformat(data_iso)
    semana_inicio = (d - timedelta(days=d.weekday())).isoformat()

    treino_doc = {
        "data": data_iso,
        "tipo": "TESTE_FTP",
        "duracao_min": body.duracao_min,
        "nome": nome,
        "descricao": descricao,
        "garmin_workout_id": gid,
        "indoor": body.forcar_indoor if body.forcar_indoor is not None else True,
    }

    # $elemMatch pra achar só o primário — um "extra" na mesma data não pode
    # ser confundido com "já existe treino" (o $set treinos.$ abaixo substitui
    # o elemento inteiro, então bater no extra errado o apagaria por completo).
    existing = await db.semanas.find_one({
        "semana_inicio": semana_inicio, "user_id": user_id,
        "treinos": {"$elemMatch": {"data": data_iso, "origem": {"$ne": "extra"}}},
    })
    if existing:
        await db.semanas.update_one(
            {
                "semana_inicio": semana_inicio, "user_id": user_id,
                "treinos": {"$elemMatch": {"data": data_iso, "origem": {"$ne": "extra"}}},
            },
            {"$set": {"treinos.$": treino_doc}},
        )
    else:
        await db.semanas.update_one(
            {"semana_inicio": semana_inicio, "user_id": user_id},
            {"$push": {"treinos": treino_doc}},
            upsert=True,
        )

    from app.services.user_service import atualizar_usuario
    await atualizar_usuario(user_id, {"ultimo_ftp_agendado": data_iso})

    return {"status": "ok", "data": data_iso, "garmin_workout_id": gid, "nome": nome}


@router.post("/treino/{semana_inicio}/{data}/reanalisar")
async def reanalisar_treino(request: Request, semana_inicio: str, data: str):
    """Regenera a análise IA de um treino já realizado sem re-baixar o .fit do Garmin."""
    from app.services.ai_service import analisar_atividade_pos_treino

    db = get_db()
    user_id = request.state.user_id

    doc = await db.semanas.find_one({"semana_inicio": semana_inicio, "user_id": user_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Semana não encontrada.")

    treino = next(
        (t for t in doc.get("treinos", []) if t["data"] == data and t.get("origem") != "extra"),
        None,
    )
    if not treino:
        raise HTTPException(status_code=404, detail="Treino não encontrado.")

    resultado = treino.get("resultado")
    if not resultado:
        raise HTTPException(status_code=400, detail="Treino não tem resultado registrado.")

    fit_filename = resultado.get("fit_file")
    fit_path = None
    if fit_filename:
        candidate = os.path.join(UPLOADS_DIR, semana_inicio, fit_filename)
        if os.path.exists(candidate):
            fit_path = candidate

    try:
        analise_ia = await analisar_atividade_pos_treino(treino, resultado, user_id, fit_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na análise IA: {e}")

    await db.semanas.update_one(
        {
            "semana_inicio": semana_inicio, "user_id": user_id,
            "treinos": {"$elemMatch": {"data": data, "origem": {"$ne": "extra"}}},
        },
        {"$set": {"treinos.$.resultado.analise_ia": analise_ia}},
    )
    return {"status": "ok", "analise_ia": analise_ia}


@router.post("/treino/{semana_inicio}/{data}/fc-invalida")
async def marcar_fc_invalida(request: Request, semana_inicio: str, data: str):
    """Marca (ou desmarca) a FC de um treino como não confiável e reavalia.

    É o caminho do portal para o mesmo ajuste que o chat faz: cinta sem
    bateria, cinta esquecida, FC travada. Body: {"invalida": bool, "motivo": str}."""
    from app.services.avaliacao_service import reavaliar_treino

    try:
        body = await request.json()
    except Exception:
        body = {}
    invalida = bool(body.get("invalida", True))
    motivo = (body.get("motivo") or "").strip() or None

    try:
        r = await reavaliar_treino(request.state.user_id, data, invalida, motivo)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao reavaliar: {e}")
    return {"status": "ok", **r}


@router.patch("/cinta-fc")
async def salvar_uso_cinta(request: Request):
    """Liga/desliga o uso de cinta cardíaca do atleta. Body: {"usa_cinta": bool,
    "reavaliar_dias": int}. Sem cinta, todo treino novo é avaliado sem FC."""
    from app.services.avaliacao_service import definir_uso_cinta, reavaliar_treinos_recentes

    body = await request.json()
    if "usa_cinta" not in body:
        raise HTTPException(status_code=400, detail="Informe usa_cinta.")
    usa_cinta = bool(body["usa_cinta"])
    await definir_uso_cinta(request.state.user_id, usa_cinta)

    dias = int(body.get("reavaliar_dias") or 0)
    reavaliados = []
    if dias > 0:
        reavaliados = await reavaliar_treinos_recentes(
            request.state.user_id, dias, not usa_cinta
        )
    return {
        "status": "ok",
        "usa_cinta": usa_cinta,
        "reavaliados": [{"data": r["data"], "nota": r.get("nota")} for r in reavaliados],
    }


@router.post("/garmin/conectar")
async def garmin_conectar(
    request: Request,
    email: str = Form(...),
    senha: str = Form(...),
):
    """Conecta a conta Garmin do usuário. Testa as credenciais, cifra a senha
    e salva no documento do usuário. Retorna {"status": "conectado"}."""
    import asyncio as _asyncio
    from garminconnect import Garmin as _Garmin
    from app.services.crypto_service import cifrar
    from app.services.user_service import atualizar_usuario
    from app.services.garmin_service import _clients

    user_id = request.state.user_id

    def _testar_login():
        api = _Garmin(email, senha)
        api.login()
        return api

    try:
        await _asyncio.to_thread(_testar_login)
    except Exception as e:
        logger.error("garmin_conectar: credenciais inválidas para user_id=%s — %s", user_id, e)
        raise HTTPException(status_code=400, detail="Credenciais Garmin inválidas. Verifique e-mail e senha.")

    # Persiste credenciais cifradas no documento do usuário
    await atualizar_usuario(user_id, {
        "integracao.tipo": "garmin",
        "integracao.garmin": {
            "email": email,
            "senha_cifrada": cifrar(senha),
        },
    })

    # Invalida o cliente cacheado para que o próximo acesso use as credenciais novas
    _clients.pop(user_id, None)

    logger.info("garmin_conectar: Garmin conectado para user_id=%s", user_id)
    return {"status": "conectado"}


@router.post("/backfill")
async def backfill_historico(request: Request, dias: int = 90):
    """Importa o histórico da plataforma conectada (Garmin ou Strava).

    É o que faz o assinante novo abrir o portal e encontrar o que já pedalou em
    vez de sete quadrados vazios — e é o que dá ao parecer fisiológico carga
    real para calibrar a primeira semana em vez de chutar.
    """
    from app.services.backfill_service import importar_historico

    user_id = request.state.user_id
    dias = max(7, min(int(dias or 90), 180))

    resultado = await importar_historico(user_id, dias)
    if resultado.get("erro") and not resultado.get("importadas"):
        raise HTTPException(status_code=400, detail=resultado["erro"])

    # A curva de potência do histórico costuma render um FTP melhor que o
    # cadastro manual — informa para o atleta ver de onde veio o número.
    ftp_novo = None
    try:
        from app.services.potencia_service import talvez_atualizar_ftp
        ftp_novo = await talvez_atualizar_ftp(user_id)
    except Exception as exc:
        logger.warning("backfill: eFTP não recalculado para %s — %s", user_id, exc)

    return {"importadas": resultado.get("importadas", 0), "dias": dias, "ftp": ftp_novo}


@router.get("/evolucao", response_class=HTMLResponse)
async def pagina_evolucao(request: Request):
    """Prova de progresso — o que segura a renovação no segundo mês.

    Não é o PMC: nada de CTL/ATL/TSB, que mentem nas primeiras semanas. São
    métricas que sobrevivem a pouco dado — carga semanal, curva de potência e
    FTP no tempo.
    """
    from app.services.user_service import get_por_id
    try:
        u = await get_por_id(request.state.user_id) or {}
    except Exception:
        u = {}
    tema = (u.get("preferencias") or {}).get("tema") or "light"
    return _PAGINA_EVOLUCAO.replace("__TEMA__", tema)


@router.get("/evolucao/dados")
async def evolucao_dados(request: Request, semanas: int = 12):
    from app.services.evolucao_service import resumo
    semanas = max(4, min(int(semanas or 12), 52))
    return await resumo(request.state.user_id, semanas)


@router.get("/curva-potencia")
async def curva_potencia(request: Request):
    """Melhores esforços dos últimos 90 dias + o FTP que sai deles."""
    from app.services.config_service import get_ftp
    from app.services.potencia_service import estimar_ftp, get_curva

    user_id = request.state.user_id
    curva = await get_curva(user_id)
    estimado, como = estimar_ftp(curva)
    ftp_atual, _ = await get_ftp(user_id)

    return {
        "curva": [
            {"duracao_s": dur, "watts": dados["watts"], "data": dados.get("data")}
            for dur, dados in sorted(curva.items())
        ],
        "ftp_estimado": estimado,
        "ftp_estimado_de": como,
        "ftp_atual": ftp_atual,
    }



@router.post("/garmin/desconectar")
async def garmin_desconectar(request: Request):
    """Remove a integração Garmin do usuário: apaga credenciais, tokenstore e cache."""
    import shutil as _shutil
    from app.services.user_service import atualizar_usuario
    from app.services.garmin_service import _clients, TOKEN_DIR

    user_id = request.state.user_id

    # Limpa credenciais no banco
    await atualizar_usuario(user_id, {
        "integracao.tipo": "none",
        "integracao.garmin": None,
    })

    # Remove tokenstore do usuário (tokens Garth em disco)
    token_dir = os.path.join(TOKEN_DIR, user_id)
    if os.path.isdir(token_dir):
        try:
            _shutil.rmtree(token_dir)
        except Exception as e:
            logger.warning("garmin_desconectar: não foi possível remover tokenstore — %s", e)

    # Remove do cache em memória
    _clients.pop(user_id, None)

    logger.info("garmin_desconectar: Garmin desconectado para user_id=%s", user_id)
    return {"status": "desconectado"}


@router.get("/zonas", response_class=HTMLResponse)
async def pagina_zonas(request: Request):
    from app.services.user_service import get_por_id
    try:
        u = await get_por_id(request.state.user_id) or {}
    except Exception:
        u = {}
    garmin_email = str(((u.get("integracao") or {}).get("garmin") or {}).get("email") or "")
    tema = (u.get("preferencias") or {}).get("tema") or "light"
    return (_PAGINA_ZONAS
            .replace("{{GARMIN_EMAIL}}", garmin_email)
            .replace("__TEMA__", tema))


@router.get("/integracao", response_class=HTMLResponse)
async def pagina_integracao(request: Request):
    """Tela self-service para conectar Garmin (login/senha) ou Strava (1 clique).
    Mostra o estado atual da integração e permite conectar/desconectar."""
    from app.services.user_service import get_por_id

    try:
        u = await get_por_id(request.state.user_id)
    except Exception:
        u = None
    if u is None:
        u = {}

    integ = u.get("integracao") or {}
    garmin = integ.get("garmin") or {}

    garmin_email = garmin.get("email")
    garmin_conectado = bool(garmin_email)

    if garmin_conectado:
        email_safe = (str(garmin_email)
                      .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        garmin_html = f"""
      <div class="status ok" style="display:block">✅ Garmin conectado <b>({email_safe})</b></div>
      <p class="hint">Importa seus treinos planejados e as atividades realizadas.</p>
      <button class="sec" onclick="desconectarGarmin()" id="btnGarminDesc">Desconectar Garmin</button>
      <div id="stGarmin" class="status"></div>"""
    else:
        garmin_html = """
      <p class="hint">Importa seus <b>treinos planejados</b> e as <b>atividades realizadas</b>. Informe o e-mail e a senha da sua conta Garmin Connect.</p>
      <form id="formGarmin" onsubmit="conectarGarmin(event)">
        <label class="fld">E-mail Garmin</label>
        <input type="email" id="g_email" name="email" autocomplete="username" required>
        <label class="fld" style="margin-top:10px">Senha Garmin</label>
        <input type="password" id="g_senha" name="senha" autocomplete="current-password" required>
        <button type="submit" id="btnGarminConn" style="margin-top:14px">Conectar Garmin</button>
      </form>
      <div id="stGarmin" class="status"></div>"""

    tema = (u.get("preferencias") or {}).get("tema") or "light"
    return (_PAGINA_INTEGRACAO
            .replace("{{GARMIN_BLOCO}}", garmin_html)
            .replace("__TEMA__", tema))


# ─── Provas (calendário de competições) ───────────────────────────────────────

class ProvaIn(BaseModel):
    nome: str
    data: str                       # YYYY-MM-DD
    local: Optional[str] = None
    distancia_km: Optional[float] = None
    altimetria_m: Optional[int] = None
    terreno: Optional[str] = None   # XCO | maratona/XCM | trail | gravel | ...
    prioridade: Optional[str] = "B"  # A | B | C
    meta: Optional[str] = None


@router.get("/provas")
async def listar_provas_rt(request: Request):
    from app.services.prova_service import listar_provas
    return await listar_provas(request.state.user_id)


@router.post("/provas")
async def criar_prova_rt(request: Request, prova: ProvaIn):
    from app.services.prova_service import criar_prova
    try:
        return await criar_prova(request.state.user_id, prova.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/provas/proxima")
async def proxima_prova_rt(request: Request):
    """Próxima prova + dias/semanas restantes, fase de periodização e focos (cache 1x/dia)."""
    from datetime import datetime
    from app.services.prova_service import (
        proxima_prova, dias_ate, semanas_ate, fase_periodizacao, FASE_LABEL, salvar_focos,
    )
    from app.services.ai_service import gerar_focos_prova

    user_id = request.state.user_id
    prova = await proxima_prova(user_id)
    if not prova:
        return {"prova": None}

    dias = dias_ate(prova["data"])
    semanas = semanas_ate(prova["data"])
    fase = fase_periodizacao(semanas)

    focos_doc = prova.get("focos") or {}
    itens = focos_doc.get("itens")
    gerado_em = focos_doc.get("gerado_em")
    precisa = (not itens) or (not gerado_em) or ((datetime.now() - gerado_em).days >= 1)
    if precisa:
        novos = await gerar_focos_prova(user_id, prova, fase, dias)
        if novos:
            itens = novos
            await salvar_focos(prova["_id"], novos)

    # Demais provas do calendário — só as futuras. O painel é sobre o que vem
    # pela frente; prova já corrida fica no histórico, em /workout/calendario.
    # Vão sem focos de propósito: gerá-los por IA para cada prova futura
    # multiplicaria o custo para informar o que só importa quando ela chegar.
    from app.services.prova_service import listar_provas
    hoje = hoje_local().isoformat()
    seguintes = [
        {
            "id": p["_id"], "nome": p.get("nome"), "data": p.get("data"),
            "local": p.get("local"), "distancia_km": p.get("distancia_km"),
            "altimetria_m": p.get("altimetria_m"), "terreno": p.get("terreno"),
            "dias_restantes": dias_ate(p["data"]),
            # Fase relativa a cada prova: reaproveitar a da próxima diria que
            # uma prova de 4 meses está em pico.
            "fase_label": FASE_LABEL.get(fase_periodizacao(semanas_ate(p["data"]))),
        }
        for p in await listar_provas(user_id)
        if p.get("data") and p["data"] >= hoje and p["_id"] != prova["_id"]
    ]

    return {
        "prova": prova,
        "dias_restantes": dias,
        "semanas_restantes": semanas,
        "fase": fase,
        "fase_label": FASE_LABEL.get(fase, fase),
        "focos": itens or [],
        "seguintes": seguintes,
    }


@router.put("/provas/{prova_id}")
async def atualizar_prova_rt(request: Request, prova_id: str, prova: ProvaIn):
    from app.services.prova_service import atualizar_prova
    try:
        await atualizar_prova(request.state.user_id, prova_id, prova.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok"}


@router.delete("/provas/{prova_id}")
async def remover_prova_rt(request: Request, prova_id: str):
    from app.services.prova_service import remover_prova
    await remover_prova(request.state.user_id, prova_id)
    return {"status": "ok"}


@router.get("/calendario", response_class=HTMLResponse)
async def pagina_calendario(request: Request):
    from app.services.user_service import get_por_id
    u = await get_por_id(request.state.user_id) or {}
    tema = (u.get("preferencias") or {}).get("tema") or "light"
    return _PAGINA_CALENDARIO.replace("__TEMA__", tema)


_OBJETIVOS_VALIDOS = {"performance_mtb", "aumentar_potencia", "base_aerobica", "manter_performance", "emagrecimento"}

@router.get("/perfil", response_class=HTMLResponse)
async def pagina_perfil(request: Request):
    import json as _json
    from app.services.user_service import get_por_id
    u = await get_por_id(request.state.user_id) or {}
    p = u.get("perfil") or {}
    pref = u.get("preferencias") or {}
    nutricao = u.get("nutricao") or {}
    val = lambda x: "" if x in (None, 0) else str(x)
    sexo = str(p.get("sexo") or "M").upper()
    obj = pref.get("objetivo") or "performance_mtb"
    metodo_zonas = (u.get("zonas") or {}).get("metodo") or "fcmax"
    garmin_email = str(((u.get("integracao") or {}).get("garmin") or {}).get("email") or "")
    academia = u.get("academia") or {}
    academia_treina = "1" if academia.get("treina") else "0"
    academia_disp_json = _json.dumps(academia.get("disponibilidade") or {})
    academia_freq = str(int(academia.get("frequencia_semanal") or 0))
    academia_nivel = str(academia.get("nivel") or "")
    usa_cinta = "0" if pref.get("sem_cinta_fc") else "1"
    tema = (pref.get("tema")) or "light"
    bike_dias = sorted({
        int(d) for d in (pref.get("dias_treino") or [])
        if str(d).isdigit() and 0 <= int(d) <= 6
    })
    bike_freq = str(int(pref.get("frequencia_semanal") or 0))
    # Meta de volume é opcional: sem meta o campo fica vazio (= "IA decide").
    from app.services.plano_semana_service import volume_semanal_do_usuario
    _volume_min = volume_semanal_do_usuario(pref)
    volume_h = f"{_volume_min / 60:g}" if _volume_min else ""
    html = (_PAGINA_PERFIL
            .replace("{{USA_CINTA}}", usa_cinta)
            .replace("{{BIKE_DIAS_JSON}}", _json.dumps(bike_dias))
            .replace("{{BIKE_FREQ}}", bike_freq)
            .replace("{{VOLUME_SEMANAL_H}}", volume_h)
            .replace("{{IDADE}}", val(p.get("idade")))
            .replace("{{PESO}}", val(p.get("peso_kg")))
            .replace("{{ALTURA}}", val(p.get("altura_cm")))
            .replace("{{SEXO_M}}", "selected" if sexo.startswith("M") else "")
            .replace("{{SEXO_F}}", "selected" if sexo.startswith("F") else "")
            .replace("{{METODO_ZONAS}}", metodo_zonas)
            .replace("{{GARMIN_EMAIL}}", garmin_email)
            .replace("{{ACADEMIA_TREINA}}", academia_treina)
            .replace("{{ACADEMIA_DISP_JSON}}", academia_disp_json)
            .replace("{{ACADEMIA_FREQ}}", academia_freq)
            .replace("{{ACADEMIA_NIVEL}}", academia_nivel)
            .replace("{{BASAL_METABOLICO}}", val(nutricao.get("basal_metabolico")))
            .replace("{{META_CALORICA}}", val(nutricao.get("meta_calorica_diaria")))
            .replace("__TEMA__", tema))
    for o in _OBJETIVOS_VALIDOS:
        html = html.replace(f"{{{{OBJ_{o}}}}}", "selected" if obj == o else "")
    return html


def _volume_semanal_min(valor) -> int | None:
    """'10' / '10,5' / '10.5' → minutos. Vazio, zero ou fora da faixa → None (sem meta)."""
    from app.services.plano_semana_service import (
        VOLUME_SEMANAL_MIN_H, VOLUME_SEMANAL_MAX_H,
    )
    try:
        horas = float(str(valor or "").replace(",", ".").strip() or 0)
    except (ValueError, TypeError):
        return None
    if not VOLUME_SEMANAL_MIN_H <= horas <= VOLUME_SEMANAL_MAX_H:
        return None
    return int(round(horas * 60 / 15)) * 15   # arredonda para 15 min


@router.post("/perfil")
async def salvar_perfil(request: Request):
    """Atualiza perfil do usuário incluindo configuração de academia."""
    from app.services.user_service import atualizar_usuario
    form = await request.form()
    try:
        idade = int(form.get("idade", 0))
        peso_kg = float(form.get("peso_kg", 0))
        altura_cm = int(form.get("altura_cm", 0))
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Dados inválidos")
    sexo = str(form.get("sexo", "M")).upper()[:1]
    objetivo = str(form.get("objetivo", "performance_mtb"))
    obj = objetivo if objetivo in _OBJETIVOS_VALIDOS else "performance_mtb"

    treina_academia = str(form.get("treina_academia", "0")) == "1"
    disponibilidade: dict = {}
    _periodos_validos = {"manha", "tarde", "noite"}
    for d in range(7):
        periodo = str(form.get(f"academia_dia_{d}", "none"))
        if periodo in _periodos_validos:
            disponibilidade[str(d)] = periodo
    try:
        frequencia_semanal = int(form.get("academia_freq", "0"))
        if frequencia_semanal not in (0, 1, 2):
            frequencia_semanal = 0
    except (ValueError, TypeError):
        frequencia_semanal = 0

    # Nível define a carga de entrada da prescrição. Valor inválido/ausente vira
    # "" e o gerador trata como iniciante — errar para o lado seguro.
    from app.services.plano_semana_service import NIVEIS_ACADEMIA
    nivel = str(form.get("academia_nivel", ""))
    if nivel not in NIVEIS_ACADEMIA:
        nivel = ""

    try:
        basal_metabolico = int(form.get("basal_metabolico") or 0) or None
    except (ValueError, TypeError):
        basal_metabolico = None
    try:
        meta_calorica_diaria = int(form.get("meta_calorica_diaria") or 0) or None
    except (ValueError, TypeError):
        meta_calorica_diaria = None

    campos: dict = {
        "perfil.idade": idade,
        "perfil.peso_kg": peso_kg,
        "perfil.altura_cm": altura_cm,
        "perfil.sexo": sexo,
        "preferencias.objetivo": obj,
    }
    # A página de perfil tem três formulários independentes (perfil, academia,
    # nutrição) e todos postam aqui, cada um mandando só o seu bloco. Gravar
    # todos os campos sempre fazia "Salvar perfil" zerar a academia inteira
    # (treina=False, dias={}, nível="") e as metas de nutrição, porque o que não
    # veio no form virava False/{}/None. Só grava o bloco que foi enviado.
    if "treina_academia" in form:
        campos.update({
            "academia.treina": treina_academia,
            "academia.disponibilidade": disponibilidade,
            "academia.frequencia_semanal": frequencia_semanal,
            "academia.nivel": nivel,
        })
    # Disponibilidade para pedalar: os dias marcados mandam; a frequência fica
    # gravada junto para o gerador saber a intenção do atleta (e para o dia em
    # que ele informar só o "quantas vezes" no cadastro).
    if "bike_dias" in form:
        try:
            bike_freq = int(form.get("bike_freq") or 0)
        except (ValueError, TypeError):
            bike_freq = 0
        bike_dias = sorted({
            int(x) for x in str(form.get("bike_dias") or "").split(",")
            if x.strip().isdigit() and 0 <= int(x) <= 6
        })
        if bike_dias:
            campos.update({
                "preferencias.dias_treino": bike_dias,
                "preferencias.frequencia_semanal": (
                    bike_freq if 1 <= bike_freq <= 7 else len(bike_dias)),
            })

    # Meta de volume semanal — OPCIONAL. Vazio/0 volta a deixar o volume por conta
    # da IA, então o campo é gravado como None (e não omitido) para poder ser
    # desligado depois de ligado.
    if "volume_semanal_h" in form:
        campos["preferencias.volume_semanal_min"] = _volume_semanal_min(
            form.get("volume_semanal_h"))

    if "basal_metabolico" in form or "meta_calorica_diaria" in form:
        campos.update({
            "nutricao.basal_metabolico": basal_metabolico,
            "nutricao.meta_calorica_diaria": meta_calorica_diaria,
        })
    await atualizar_usuario(request.state.user_id, campos)
    return {"status": "ok"}


@router.patch("/tema")
async def salvar_tema(request: Request):
    from app.services.user_service import atualizar_usuario
    body = await request.json()
    tema = body.get("tema", "light")
    if tema not in ("light", "dark"):
        raise HTTPException(status_code=400, detail="Tema inválido")
    await atualizar_usuario(request.state.user_id, {"preferencias.tema": tema})
    return {"status": "ok"}


@router.post("/fit/{semana_inicio}/{data}")
async def upload_fit(request: Request, semana_inicio: str, data: str, arquivo: UploadFile = File(...)):
    user_id = request.state.user_id
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
    doc = await db.semanas.find_one({"semana_inicio": semana_inicio, "user_id": user_id})

    # inclui descrição já salva no banco para ajudar a IA a classificar
    descricao_existente = None
    if doc:
        for t in doc.get("treinos", []):
            if t.get("data") == data and t.get("origem") != "extra":
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
            "user_id": user_id,
            "objetivo": "",
            "treinos": [novo_treino],
        })
    else:
        treino_existe = any(
            t.get("data") == data and t.get("origem") != "extra"
            for t in doc.get("treinos", [])
        )
        if treino_existe:
            # apenas campos com valor — preserva descricao já salva
            fields = {f"treinos.$.{k}": v for k, v in novo_treino.items() if v is not None}
            await db.semanas.update_one(
                {
                    "semana_inicio": semana_inicio, "user_id": user_id,
                    "treinos": {"$elemMatch": {"data": data, "origem": {"$ne": "extra"}}},
                },
                {"$set": fields},
            )
        else:
            await db.semanas.update_one(
                {"semana_inicio": semana_inicio, "user_id": user_id},
                {"$push": {"treinos": novo_treino}},
            )

    return {"status": "ok", "fit_file": safe_name, **analise}


@router.delete("/fit/{semana_inicio}/{data}")
async def remover_fit(request: Request, semana_inicio: str, data: str):
    dest_path = os.path.join(UPLOADS_DIR, semana_inicio, f"{data}.fit")
    if os.path.exists(dest_path):
        os.remove(dest_path)
    db = get_db()
    await db.semanas.update_one(
        {
            "semana_inicio": semana_inicio, "user_id": request.state.user_id,
            "treinos": {"$elemMatch": {"data": data, "origem": {"$ne": "extra"}}},
        },
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


# ── "extra": segundo (ou terceiro...) treino no mesmo dia ────────────────────
# Espécie totalmente separada do treino principal: gerida só pelo usuário no
# painel, nunca sincroniza com o Garmin, nunca é tocada pela IA ou pelo botão
# "Salvar Semana". Identificada por origem="extra" + id próprio (a data deixa
# de ser única quando há um extra). Ver plano em
# /Users/marcianocadore/.claude/plans/whimsical-munching-whisper.md.

class ExtraCreateBody(BaseModel):
    tipo: TipoTreino
    duracao_min: Optional[int] = None
    descricao: Optional[str] = None


class ExtraUpdateBody(BaseModel):
    tipo: Optional[TipoTreino] = None
    duracao_min: Optional[int] = None
    descricao: Optional[str] = None
    concluido: Optional[bool] = None


@router.post("/treino/{semana_inicio}/{data}/extra")
async def criar_treino_extra(request: Request, semana_inicio: str, data: str, body: ExtraCreateBody):
    db = get_db()
    entry = {
        "id": uuid.uuid4().hex[:12],
        "origem": "extra",
        "data": data,
        "tipo": body.tipo,
        "duracao_min": body.duracao_min,
        "descricao": body.descricao,
        "concluido": False,
    }
    await db.semanas.update_one(
        {"semana_inicio": semana_inicio, "user_id": request.state.user_id},
        {"$push": {"treinos": entry}},
        upsert=True,
    )
    return entry


@router.patch("/treino/{semana_inicio}/{data}/extra/{extra_id}")
async def editar_treino_extra(
    request: Request, semana_inicio: str, data: str, extra_id: str, body: ExtraUpdateBody,
):
    db = get_db()
    campos = body.model_dump(exclude_none=True)
    if not campos:
        return {"status": "sem alteracoes"}
    fields = {f"treinos.$.{k}": v for k, v in campos.items()}
    # id já é único por si só — não precisa de $elemMatch aqui.
    result = await db.semanas.update_one(
        {"semana_inicio": semana_inicio, "user_id": request.state.user_id, "treinos.id": extra_id},
        {"$set": fields},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Treino extra não encontrado.")
    return {"status": "ok", **campos}


@router.delete("/treino/{semana_inicio}/{data}/extra/{extra_id}")
async def remover_treino_extra(request: Request, semana_inicio: str, data: str, extra_id: str):
    db = get_db()
    result = await db.semanas.update_one(
        {"semana_inicio": semana_inicio, "user_id": request.state.user_id},
        {"$pull": {"treinos": {"id": extra_id, "origem": "extra"}}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Treino extra não encontrado.")
    return {"status": "removido"}


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
  nav { background:var(--green); color:#fff; padding:14px 20px; display:flex; align-items:center; gap:10px; box-shadow:0 2px 8px rgba(0,0,0,.2); }
  nav .logo { font-weight:800; font-size:1.1rem; }
  nav a { margin-left:auto; color:rgba(255,255,255,.85); text-decoration:none; font-size:.9rem; font-weight:600; white-space:nowrap; }
  nav a:hover { color:#fff; text-decoration:underline; }
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
  .metodo-tabs { display:flex; gap:8px; margin:10px 0 14px; }
  .tab-btn { flex:1; padding:9px; border-radius:9px; border:1.5px solid var(--border); background:#fff; font-size:.88rem; font-weight:600; cursor:pointer; color:var(--muted); transition:.15s; }
  .tab-btn.active { background:var(--green); color:#fff; border-color:var(--green); }
  .tab-btn:hover:not(.active) { border-color:var(--green); color:var(--green); }
  .metodo-desc { font-size:.85rem; color:#374151; line-height:1.6; background:#f9fafb; border-radius:9px; padding:11px 13px; border-left:3px solid var(--green); }
  .metodo-desc b { color:var(--text); }
  .garmin-badge { display:inline-flex; align-items:center; gap:5px; background:#e8f5e9; color:#2e7d32; border-radius:20px; padding:3px 10px; font-size:.75rem; font-weight:700; }
  .garmin-warn { background:#fef3c7; border:1.5px solid #fbbf24; border-radius:9px; padding:10px 13px; font-size:.84rem; color:#92400e; margin-bottom:12px; }
  .garmin-warn a { color:#b45309; font-weight:700; text-decoration:none; }
  .garmin-warn a:hover { text-decoration:underline; }
  [data-theme="dark"] { --bg:#111827; --card:#1f2937; --text:#e5e7eb; --muted:#9ca3af; --border:#374151; --green:#1db39e; }
  [data-theme="dark"] body { background:var(--bg); color:var(--text); }
  [data-theme="dark"] .card { background:var(--card); }
  [data-theme="dark"] input, [data-theme="dark"] select { background:#111827; color:var(--text); border-color:var(--border); }
  [data-theme="dark"] .garmin-warn { background:#2a1900; border-color:#7c3a00; color:#fbbf24; }
  [data-theme="dark"] .garmin-warn a { color:#fbbf24; }
  [data-theme="dark"] .metodo-desc { background:#111827; border-left-color:var(--green); color:var(--text); }
  [data-theme="dark"] .tab-btn { background:#1f2937; color:var(--muted); border-color:var(--border); }
  [data-theme="dark"] .tab-btn.active { background:var(--green); color:#fff; }
  [data-theme="dark"] .zona-row input { background:#111827; }
</style>
  <script>(function(){var t=localStorage.getItem('mtb-tema')||'__TEMA__';document.documentElement.setAttribute('data-theme',t)})();</script>
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
    <h2>⚙️ Como calcular suas zonas?</h2>
    <p class="hint">Existem dois métodos. Não sabe qual usar? Comece pelo <b>% FC Máxima</b> — é o mais simples.</p>
    <div class="metodo-tabs">
      <button class="tab-btn active" id="tab-fcmax" onclick="setMetodo('fcmax')">% FC Máxima</button>
      <button class="tab-btn" id="tab-ll" onclick="setMetodo('ll')">% Limiar Lático (LL)</button>
    </div>
    <div id="desc-fcmax" class="metodo-desc">
      <b>Simples e popular</b> — usa o maior batimento cardíaco que seu coração consegue atingir.
      Ideal para quem está começando. Estimativa rápida: <b>220 − sua idade</b>. Para medir de verdade:
      faça um sprint de 3 min no limite e anote a FC mais alta que aparecer.
    </div>
    <div id="desc-ll" class="metodo-desc" style="display:none">
      <b>Mais preciso</b> — usa o ponto onde seu corpo começa a acumular ácido lático e você
      fica ofegante sem conseguir manter o ritmo por muito tempo.
      <b>Como medir:</b> pedala em ritmo forte e constante por 30 min e anota a FC média dos <em>últimos 20 min</em>.
      Não sabe? Estime como <b>90% da sua FC máxima</b>.
    </div>
    <div class="duo" style="margin-top:14px">
      <div>
        <label class="fld">FC Máxima (bpm)</label>
        <input type="number" id="fc_max" min="100" max="230" placeholder="ex: 185">
      </div>
      <div id="ll-field" style="display:none">
        <label class="fld">Limiar Lático (bpm)</label>
        <input type="number" id="limiar" min="100" max="210" placeholder="ex: 165">
      </div>
    </div>
    <button class="sec" onclick="calcularZonasAuto()" style="margin-top:12px">⚡ Calcular zonas automaticamente</button>
    <div id="st-calc" class="status"></div>
  </div>

  <div class="card">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">
      <h2 style="margin-bottom:0">📥 Importar do Garmin</h2>
      <span id="garmin-badge" class="garmin-badge" style="display:none">✓ Conectado</span>
    </div>
    <p class="hint">Puxa as zonas oficiais do seu perfil de ciclismo direto da conta Garmin — sem print, sem IA. É o jeito mais confiável.</p>
    <div id="garmin-warn" class="garmin-warn" style="display:none">
      ⚠️ Garmin não conectado. <a href="/workout/integracao">Conectar agora →</a>
    </div>
    <button id="btnGarmin" onclick="importarGarmin()">📥 Importar zonas do Garmin</button>
    <div id="stGarmin" class="status"></div>
  </div>

  <div class="card">
    <h2>📷 Ler de uma imagem</h2>
    <p class="hint">Alternativa: tire um print da tela de zonas de FC no app/relógio Garmin e envie aqui — a IA preenche os campos. Confira antes de salvar.</p>
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
    <div style="margin-top:18px">
      <button id="btnSalvar" onclick="salvar()">💾 Salvar zonas</button>
    </div>
    <div id="st" class="status"></div>
  </div>
</main>
<script>
  const CORES = ['z1','z2','z3','z4','z5'];
  const GARMIN_EMAIL = '{{GARMIN_EMAIL}}';
  let _metodo = 'fcmax';

  function configurarGarmin() {
    const badge = document.getElementById('garmin-badge');
    const warn = document.getElementById('garmin-warn');
    const btn = document.getElementById('btnGarmin');
    if (GARMIN_EMAIL) {
      badge.textContent = '✓ ' + GARMIN_EMAIL;
      badge.style.display = '';
      btn.textContent = '🔄 Reimportar zonas do Garmin';
    } else {
      warn.style.display = '';
      btn.disabled = true;
    }
  }
  configurarGarmin();

  function setMetodo(m) {
    _metodo = m;
    document.getElementById('tab-fcmax').classList.toggle('active', m === 'fcmax');
    document.getElementById('tab-ll').classList.toggle('active', m === 'll');
    document.getElementById('desc-fcmax').style.display = m === 'fcmax' ? '' : 'none';
    document.getElementById('desc-ll').style.display = m === 'll' ? '' : 'none';
    document.getElementById('ll-field').style.display = m === 'll' ? '' : 'none';
  }

  function calcularZonasAuto() {
    const fc = Number(document.getElementById('fc_max').value);
    const st = document.getElementById('st-calc');
    if (_metodo === 'fcmax') {
      if (!fc || fc < 100 || fc > 230) { st.className='status err'; st.textContent='⚠️ Informe a FC Máxima (100–230 bpm).'; return; }
      const pcts = [[0.64,0.76],[0.77,0.85],[0.86,0.89],[0.90,0.94],[0.95,1.00]];
      renderZonas(pcts.map(([mn,mx],i) => ({zona:i+1,min:Math.round(fc*mn),max:i===4?fc:Math.round(fc*mx)})));
      st.className='status ok'; st.textContent='✅ Calculado por % FC Máxima. Revise e salve.';
    } else {
      const lim = Number(document.getElementById('limiar').value);
      if (!lim || lim < 100 || lim > 210) { st.className='status err'; st.textContent='⚠️ Informe o Limiar Lático (100–210 bpm).'; return; }
      const pcts = [[0.65,0.84],[0.85,0.89],[0.90,0.94],[0.95,0.99],[1.00,1.05]];
      renderZonas(pcts.map(([mn,mx],i) => ({zona:i+1,min:Math.round(lim*mn),max:i===4?(fc&&fc>lim?fc:Math.round(lim*mx)):Math.round(lim*mx)})));
      st.className='status ok'; st.textContent='✅ Calculado por % Limiar Lático. Revise e salve.';
    }
  }

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
    const lim = document.getElementById('limiar') ? document.getElementById('limiar').value : '';
    return { fc_max: fc ? Number(fc) : null, limiar: lim ? Number(lim) : null, metodo: _metodo, zonas };
  }
  function aplicar(d) {
    renderZonas(d.zonas);
    if (d.fc_max != null) document.getElementById('fc_max').value = d.fc_max;
    const limEl = document.getElementById('limiar');
    if (limEl && d.limiar != null) limEl.value = d.limiar;
    if (d.metodo) setMetodo(d.metodo);
  }
  async function carregar() {
    try {
      const r = await fetch('/workout/zonas/dados');
      aplicar(await r.json());
    } catch(e) { renderZonas([]); }
  }
  async function importarGarmin() {
    const btn = document.getElementById('btnGarmin'), st = document.getElementById('stGarmin');
    btn.disabled = true; btn.textContent = 'Importando...'; st.className='status info'; st.textContent='📡 Lendo zonas do Garmin...';
    try {
      const r = await fetch('/workout/zonas/importar-garmin', { method:'POST' });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Erro');
      aplicar(d);
      const esporte = d.sport ? ' (perfil ' + d.sport.toLowerCase() + ')' : '';
      st.className='status ok'; st.textContent='✅ Zonas importadas do Garmin' + esporte + '! Confira e clique em Salvar.';
    } catch(e) { st.className='status err'; st.textContent='❌ ' + e.message; }
    finally { btn.disabled=false; btn.textContent='📥 Importar zonas do Garmin'; }
  }
  async function lerImagem() {
    const inp = document.getElementById('img'), st = document.getElementById('stImg'), btn = document.getElementById('btnLer');
    if (!inp.files.length) { st.className='status err'; st.textContent='⚠️ Escolha uma imagem primeiro.'; return; }
    btn.disabled = true; btn.textContent = 'Lendo...'; st.className='status info'; st.textContent='🤖 Analisando a imagem...';
    try {
      const fd = new FormData(); fd.append('imagem', inp.files[0]);
      const r = await fetch('/workout/zonas/extrair', { method:'POST', body: fd });
      const d = await r.json();
      if (!r.ok) { const err = new Error(d.detail || 'Erro'); err.cota = (r.status === 429); throw err; }
      aplicar(d);
      st.className='status ok'; st.textContent='✅ Zonas preenchidas! Confira os valores e clique em Salvar.';
    } catch(e) {
      if (e.cota) { st.className='status info'; st.textContent='⏳ ' + e.message; }
      else { st.className='status err'; st.textContent='❌ ' + e.message; }
    }
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
      const sync = (d.garmin_sync && d.garmin_sync.ok)
        ? ' e sincronizadas com o Garmin 📤'
        : ' (não consegui sincronizar com o Garmin agora — tente de novo)';
      st.className = (d.garmin_sync && d.garmin_sync.ok) ? 'status ok' : 'status err';
      st.textContent = '✅ Zonas salvas' + sync;
    } catch(e) { st.className='status err'; st.textContent='❌ ' + e.message; }
    finally { btn.disabled=false; btn.textContent='💾 Salvar zonas'; }
  }
  carregar();
</script>
</body>
</html>"""


_PAGINA_INTEGRACAO = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MTB Nutrition — Conectar dispositivo</title>
<style>
  * { box-sizing:border-box; margin:0; padding:0; }
  :root { --green:#0e8a7d; --text:#1f2937; --muted:#6b7280; --border:#e5e7eb; --bg:#f0f2f5; }
  body { font-family:-apple-system,BlinkMacSystemFont,sans-serif; background:var(--bg); color:var(--text); }
  nav { background:var(--green); color:#fff; padding:14px 20px; display:flex; align-items:center; gap:10px; box-shadow:0 2px 8px rgba(0,0,0,.2); }
  nav .logo { font-weight:800; font-size:1.1rem; }
  nav a { margin-left:auto; color:rgba(255,255,255,.85); text-decoration:none; font-size:.9rem; font-weight:600; white-space:nowrap; }
  nav a:hover { color:#fff; text-decoration:underline; }
  main { max-width:560px; margin:0 auto; padding:24px 16px 60px; }
  h1 { font-size:1.4rem; margin-bottom:6px; }
  .sub { color:var(--muted); margin-bottom:22px; font-size:.92rem; line-height:1.5; }
  .card { background:#fff; border-radius:14px; padding:22px; box-shadow:0 1px 4px rgba(0,0,0,.06); margin-bottom:18px; }
  .card h2 { font-size:1.05rem; color:var(--green); margin-bottom:6px; }
  p.hint { font-size:.85rem; color:var(--muted); margin:6px 0 14px; line-height:1.45; }
  label.fld { display:block; font-size:.72rem; color:var(--muted); text-transform:uppercase; letter-spacing:.4px; margin-bottom:4px; }
  input[type=email], input[type=password] { width:100%; border:1.5px solid var(--border); border-radius:9px; padding:11px; font-size:1rem; outline:none; font-family:inherit; }
  input:focus { border-color:var(--green); }
  button { width:100%; padding:14px; background:var(--green); color:#fff; border:none; border-radius:10px; font-size:1rem; font-weight:700; cursor:pointer; }
  button:hover:not(:disabled) { background:#0c7669; }
  button:disabled { opacity:.6; cursor:not-allowed; }
  button.sec { background:#374151; }
  button.sec:hover:not(:disabled) { background:#1f2937; }
  .status { margin-top:14px; padding:12px; border-radius:10px; font-size:.9rem; display:none; }
  .ok { background:#e8f5e9; color:#2e7d32; display:block; }
  .err { background:#fdecea; color:#c62828; display:block; }
  .info { background:#eef6ff; color:#1d4ed8; display:block; }
  .banner { padding:12px 14px; border-radius:10px; font-size:.9rem; font-weight:600; margin-bottom:18px; }
  .banner.ok { background:#e8f5e9; color:#2e7d32; }
  .banner.err { background:#fdecea; color:#c62828; }
  [data-theme="dark"] { --bg:#111827; --card:#1f2937; --text:#e5e7eb; --muted:#9ca3af; --border:#374151; --green:#1db39e; }
  [data-theme="dark"] body { background:var(--bg); color:var(--text); }
  [data-theme="dark"] .card { background:var(--card); }
  [data-theme="dark"] input, [data-theme="dark"] select { background:#111827; color:var(--text); border-color:var(--border); }
</style>
  <script>(function(){var t=localStorage.getItem('mtb-tema')||'__TEMA__';document.documentElement.setAttribute('data-theme',t)})();</script>
</head>
<body>
<nav>
  <span style="font-size:1.4rem">⌚</span>
  <span class="logo">MTB Nutrition</span>
  <a href="/portal/">← Voltar ao portal</a>
</nav>
<main>
  <h1>Conectar dispositivo</h1>
  <p class="sub">Conecte seu Garmin para importar treinos planejados e atividades automaticamente. Você só precisa fazer isso uma vez.</p>

  <div id="bannerBox"></div>

  <div class="card">
    <h2>⌚ Garmin Connect</h2>
    {{GARMIN_BLOCO}}
  </div>
</main>
<script>
  function getMonday(d) {
    const day = d.getDay();
    const diff = day === 0 ? -6 : 1 - day;
    const m = new Date(d);
    m.setDate(d.getDate() + diff);
    m.setHours(0,0,0,0);
    return m;
  }
  function iso(d) { return d.toISOString().split('T')[0]; }
  function segundaAtualISO() { return iso(getMonday(new Date())); }

  // Importa 90 dias de histórico. Demora (baixa e analisa um .fit por sessão),
  // então a mensagem explica o que está acontecendo em vez de deixar a tela
  // parada — e uma falha aqui nunca desfaz a conexão que acabou de dar certo.
  async function importarHistorico(st) {
    st.className = 'status info';
    st.textContent = '📥 Importando seus últimos 90 dias… isso pode levar um minuto.';
    try {
      const r = await fetch('/workout/backfill?dias=90', { method: 'POST' });
      if (!r.ok) throw new Error('backfill');
      const d = await r.json();
      let msg = d.importadas
        ? `✅ ${d.importadas} treino${d.importadas > 1 ? 's' : ''} importado${d.importadas > 1 ? 's' : ''} do seu histórico.`
        : '✅ Conectado! Não encontrei treinos anteriores para importar.';
      if (d.ftp && d.ftp.ftp) {
        msg += ` Seu FTP foi estimado em ${d.ftp.ftp}W (${d.ftp.origem}).`;
      }
      st.className = 'status ok';
      st.textContent = msg;
    } catch (e) {
      st.className = 'status ok';
      st.textContent = '✅ Conectado! (não consegui importar o histórico agora — dá para tentar depois)';
    }
  }

  async function conectarGarmin(ev) {
    ev.preventDefault();
    const btn = document.getElementById('btnGarminConn');
    const st = document.getElementById('stGarmin');
    btn.disabled = true; btn.textContent = 'Conectando...';
    st.className = 'status info'; st.textContent = '🔐 Verificando credenciais...';
    try {
      const fd = new FormData();
      fd.append('email', document.getElementById('g_email').value);
      fd.append('senha', document.getElementById('g_senha').value);
      const r = await fetch('/workout/garmin/conectar', { method:'POST', body: fd });
      if (r.status === 400) { st.className='status err'; st.textContent='❌ Credenciais inválidas. Verifique e-mail e senha.'; return; }
      if (!r.ok) throw new Error('Erro ao conectar');
      st.className='status ok'; st.textContent='✅ Conectado! Sincronizando seus treinos…';
      // Sync inicial best-effort
      try { await fetch('/workout/garmin/sync/' + segundaAtualISO(), { method:'POST' }); } catch(e) {}
      await importarHistorico(st);
      setTimeout(() => location.reload(), 1500);
    } catch(e) {
      st.className='status err'; st.textContent='❌ ' + e.message;
    } finally {
      btn.disabled = false; btn.textContent = 'Conectar Garmin';
    }
  }

  async function desconectarGarmin() {
    const btn = document.getElementById('btnGarminDesc');
    const st = document.getElementById('stGarmin');
    if (btn) { btn.disabled = true; btn.textContent = 'Desconectando...'; }
    try {
      const r = await fetch('/workout/garmin/desconectar', { method:'POST' });
      if (!r.ok) throw new Error('Erro');
      location.reload();
    } catch(e) {
      st.className='status err'; st.textContent='❌ ' + e.message;
      if (btn) { btn.disabled = false; btn.textContent = 'Desconectar Garmin'; }
    }
  }

</script>
</body>
</html>"""


_PAGINA_CALENDARIO = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MTB Nutrition — Calendário de provas</title>
<style>
  * { box-sizing:border-box; margin:0; padding:0; }
  :root { --green:#0e8a7d; --text:#1f2937; --muted:#6b7280; --border:#e5e7eb; --bg:#f0f2f5; }
  body { font-family:-apple-system,BlinkMacSystemFont,sans-serif; background:var(--bg); color:var(--text); }
  nav { background:var(--green); color:#fff; padding:14px 20px; display:flex; align-items:center; gap:10px; box-shadow:0 2px 8px rgba(0,0,0,.2); }
  nav .logo { font-weight:800; font-size:1.1rem; }
  nav a { margin-left:auto; color:rgba(255,255,255,.85); text-decoration:none; font-size:.9rem; font-weight:600; white-space:nowrap; }
  nav a:hover { color:#fff; text-decoration:underline; }
  main { max-width:620px; margin:0 auto; padding:24px 16px 60px; }
  h1 { font-size:1.4rem; margin-bottom:6px; }
  .sub { color:var(--muted); margin-bottom:22px; font-size:.92rem; }
  .card { background:#fff; border-radius:14px; padding:22px; box-shadow:0 1px 4px rgba(0,0,0,.06); margin-bottom:18px; }
  .card h2 { font-size:1.05rem; color:var(--green); margin-bottom:14px; }
  label.fld { display:block; font-size:.72rem; color:var(--muted); text-transform:uppercase; letter-spacing:.4px; margin-bottom:3px; margin-top:12px; }
  input, select, textarea { width:100%; border:1.5px solid var(--border); border-radius:9px; padding:10px; font-size:1rem; outline:none; font-family:inherit; }
  input:focus, select:focus, textarea:focus { border-color:var(--green); }
  textarea { resize:vertical; min-height:54px; font-size:.92rem; }
  .duo { display:flex; gap:12px; }
  .duo > div { flex:1; }
  button { width:100%; padding:14px; background:var(--green); color:#fff; border:none; border-radius:10px; font-size:1rem; font-weight:700; cursor:pointer; margin-top:16px; }
  button:hover:not(:disabled) { background:#0c7669; }
  button:disabled { opacity:.6; cursor:not-allowed; }
  button.sec { background:#374151; }
  .status { margin-top:14px; padding:12px; border-radius:10px; font-size:.9rem; display:none; }
  .ok { background:#e8f5e9; color:#2e7d32; display:block; }
  .err { background:#fdecea; color:#c62828; display:block; }
  .prova-item { border:1px solid var(--border); border-radius:12px; padding:14px; margin-bottom:12px; }
  .prova-item.passada { opacity:.55; }
  .prova-top { display:flex; align-items:center; gap:8px; }
  .prova-nome { font-weight:800; font-size:1rem; flex:1; }
  .prio { font-size:.7rem; font-weight:800; color:#fff; border-radius:6px; padding:2px 7px; }
  .prio.A { background:#ef4444; } .prio.B { background:#f59e0b; } .prio.C { background:#9ca3af; }
  .prova-meta { font-size:.85rem; color:var(--muted); margin-top:5px; }
  .prova-count { font-size:.82rem; color:var(--green); font-weight:700; margin-top:4px; }
  .prova-acoes { display:flex; gap:8px; margin-top:10px; }
  .prova-acoes button { width:auto; flex:1; margin-top:0; padding:8px; font-size:.82rem; }
  .prova-acoes .del { background:#fdecea; color:#c62828; }
  .vazio { color:var(--muted); font-size:.9rem; text-align:center; padding:18px 0; }
  [data-theme="dark"] { --bg:#111827; --card:#1f2937; --text:#e5e7eb; --muted:#9ca3af; --border:#374151; --green:#1db39e; }
  [data-theme="dark"] body { background:var(--bg); color:var(--text); }
  [data-theme="dark"] .card { background:var(--card); }
  [data-theme="dark"] input, [data-theme="dark"] select, [data-theme="dark"] textarea { background:#111827; color:var(--text); border-color:var(--border); }
  [data-theme="dark"] .prova-card { background:var(--card); border-color:var(--border); }
  [data-theme="dark"] .prova-acoes button { background:var(--card); border-color:var(--border); color:var(--text); }
</style>
  <script>(function(){var t=localStorage.getItem('mtb-tema')||'__TEMA__';document.documentElement.setAttribute('data-theme',t)})();</script>
</head>
<body>
<nav>
  <span style="font-size:1.4rem">📅</span>
  <span class="logo">MTB Nutrition</span>
  <a href="/portal/">← Voltar ao portal</a>
</nav>
<main>
  <h1>Calendário de provas</h1>
  <p class="sub">Cadastre as provas que vai disputar. A IA usa a próxima prova para periodizar seus treinos (base → construção → pico → polimento) e apontar focos de melhoria.</p>

  <div class="card">
    <h2 id="formTitulo">➕ Nova prova</h2>
    <form id="form" onsubmit="salvar(event)">
      <input type="hidden" id="prova_id">
      <label class="fld">Nome da prova *</label>
      <input id="nome" required placeholder="Ex.: Copa MTB Serra — Etapa 3">
      <div class="duo">
        <div>
          <label class="fld">Data *</label>
          <input id="data" type="date" required>
        </div>
        <div>
          <label class="fld">Prioridade</label>
          <select id="prioridade">
            <option value="A">A — principal</option>
            <option value="B" selected>B — importante</option>
            <option value="C">C — treino/preparação</option>
          </select>
        </div>
      </div>
      <label class="fld">Local</label>
      <input id="local" placeholder="Cidade / clube">
      <div class="duo">
        <div>
          <label class="fld">Distância (km)</label>
          <input id="distancia_km" type="number" step="0.1" min="0" placeholder="Ex.: 45">
        </div>
        <div>
          <label class="fld">Altimetria (m)</label>
          <input id="altimetria_m" type="number" step="1" min="0" placeholder="Ex.: 1200">
        </div>
      </div>
      <label class="fld">Tipo de terreno</label>
      <select id="terreno">
        <option value="">—</option>
        <option>XCO (cross-country olímpico)</option>
        <option>Maratona / XCM</option>
        <option>Trail / técnico</option>
        <option>Gravel / estrada de terra</option>
        <option>Subida longa</option>
        <option>Misto</option>
      </select>
      <label class="fld">Meta / observações</label>
      <textarea id="meta" placeholder="Ex.: Terminar entre os 10 primeiros; melhorar nas subidas longas."></textarea>
      <button type="submit" id="btnSalvar">Salvar prova</button>
      <button type="button" class="sec" id="btnCancelar" style="display:none" onclick="resetForm()">Cancelar edição</button>
      <div id="st" class="status"></div>
    </form>
  </div>

  <div class="card">
    <h2>Minhas provas</h2>
    <div id="lista"><div class="vazio">Carregando…</div></div>
  </div>
</main>

<script>
let PROVAS = [];

function hojeISO(){ return new Date().toISOString().slice(0,10); }

function diasAte(d){
  const a = new Date(d + 'T00:00'), b = new Date(hojeISO() + 'T00:00');
  return Math.round((a - b) / 86400000);
}

function fmtData(d){
  const [y,m,dd] = d.split('-');
  return dd + '/' + m + '/' + y;
}

function countdownTxt(dias){
  if (dias < 0) return 'Realizada';
  if (dias === 0) return '🏁 É hoje!';
  if (dias === 1) return 'Falta 1 dia';
  return 'Faltam ' + dias + ' dias';
}

async function carregar(){
  const r = await fetch('/workout/provas');
  PROVAS = r.ok ? await r.json() : [];
  render();
}

function render(){
  const el = document.getElementById('lista');
  if (!PROVAS.length){ el.innerHTML = '<div class="vazio">Nenhuma prova cadastrada ainda.</div>'; return; }
  el.innerHTML = PROVAS.map(p => {
    const dias = diasAte(p.data);
    const meta = [];
    if (p.local) meta.push('📍 ' + p.local);
    if (p.distancia_km) meta.push(p.distancia_km + ' km');
    if (p.altimetria_m) meta.push(p.altimetria_m + ' m');
    if (p.terreno) meta.push(p.terreno);
    const esc = s => (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    return `<div class="prova-item ${dias < 0 ? 'passada' : ''}">
      <div class="prova-top">
        <span class="prova-nome">${esc(p.nome)}</span>
        <span class="prio ${p.prioridade || 'B'}">${p.prioridade || 'B'}</span>
      </div>
      <div class="prova-count">${fmtData(p.data)} · ${countdownTxt(dias)}</div>
      ${meta.length ? `<div class="prova-meta">${esc(meta.join('  ·  '))}</div>` : ''}
      ${p.meta ? `<div class="prova-meta">🎯 ${esc(p.meta)}</div>` : ''}
      <div class="prova-acoes">
        <button onclick="editar('${p._id}')">✏️ Editar</button>
        <button class="del" onclick="remover('${p._id}')">🗑️ Excluir</button>
      </div>
    </div>`;
  }).join('');
}

function editar(id){
  const p = PROVAS.find(x => x._id === id);
  if (!p) return;
  document.getElementById('prova_id').value = p._id;
  document.getElementById('nome').value = p.nome || '';
  document.getElementById('data').value = p.data || '';
  document.getElementById('prioridade').value = p.prioridade || 'B';
  document.getElementById('local').value = p.local || '';
  document.getElementById('distancia_km').value = p.distancia_km ?? '';
  document.getElementById('altimetria_m').value = p.altimetria_m ?? '';
  document.getElementById('terreno').value = p.terreno || '';
  document.getElementById('meta').value = p.meta || '';
  document.getElementById('formTitulo').textContent = '✏️ Editar prova';
  document.getElementById('btnCancelar').style.display = 'block';
  window.scrollTo({top:0, behavior:'smooth'});
}

function resetForm(){
  document.getElementById('form').reset();
  document.getElementById('prova_id').value = '';
  document.getElementById('prioridade').value = 'B';
  document.getElementById('formTitulo').textContent = '➕ Nova prova';
  document.getElementById('btnCancelar').style.display = 'none';
  document.getElementById('st').className = 'status';
}

async function salvar(ev){
  ev.preventDefault();
  const st = document.getElementById('st'), btn = document.getElementById('btnSalvar');
  const id = document.getElementById('prova_id').value;
  const num = v => v === '' ? null : Number(v);
  const body = {
    nome: document.getElementById('nome').value.trim(),
    data: document.getElementById('data').value,
    prioridade: document.getElementById('prioridade').value,
    local: document.getElementById('local').value.trim() || null,
    distancia_km: num(document.getElementById('distancia_km').value),
    altimetria_m: num(document.getElementById('altimetria_m').value),
    terreno: document.getElementById('terreno').value || null,
    meta: document.getElementById('meta').value.trim() || null,
  };
  btn.disabled = true; btn.textContent = 'Salvando…';
  try {
    const url = id ? '/workout/provas/' + id : '/workout/provas';
    const r = await fetch(url, {
      method: id ? 'PUT' : 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error((await r.json().catch(()=>({}))).detail || 'Erro ao salvar');
    st.className = 'status ok'; st.textContent = '✅ Prova salva!';
    resetForm();
    await carregar();
  } catch(e){
    st.className = 'status err'; st.textContent = '❌ ' + e.message;
  } finally {
    btn.disabled = false; btn.textContent = 'Salvar prova';
  }
}

async function remover(id){
  if (!confirm('Excluir esta prova?')) return;
  await fetch('/workout/provas/' + id, { method:'DELETE' });
  await carregar();
}

carregar();
</script>
</body>
</html>"""


_PAGINA_PERFIL = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MTB Nutrition — Meu perfil</title>
<style>
  * { box-sizing:border-box; margin:0; padding:0; }
  :root { --green:#128c7e; --text:#1f2937; --muted:#6b7280; --border:#e5e7eb; --bg:#f0f2f5; }
  body { font-family:-apple-system,BlinkMacSystemFont,sans-serif; background:var(--bg); color:var(--text); }
  nav { background:var(--green); color:#fff; padding:14px 20px; display:flex; align-items:center; gap:10px; box-shadow:0 2px 8px rgba(0,0,0,.2); }
  nav .logo { font-weight:800; font-size:1.1rem; }
  nav a { margin-left:auto; color:rgba(255,255,255,.85); text-decoration:none; font-size:.9rem; font-weight:600; white-space:nowrap; }
  nav a:hover { color:#fff; text-decoration:underline; }
  main { max-width:560px; margin:0 auto; padding:24px 16px 60px; }
  h1 { font-size:1.4rem; margin-bottom:6px; }
  .sub { color:var(--muted); margin-bottom:22px; font-size:.92rem; }
  .section-title { font-size:1rem; font-weight:800; color:var(--text); margin:28px 0 12px; display:flex; align-items:center; gap:8px; }
  .section-title::after { content:''; flex:1; height:1px; background:var(--border); }
  /* No desktop as configurações viram duas colunas — a página tem muito bloco
     para caber num scroll só. No celular continua tudo empilhado. */
  @media (min-width:1000px) {
    main { max-width:1140px; }
    .cols { display:grid; grid-template-columns:1fr 1fr; gap:0 28px; align-items:start; }
    .col > .section-title:first-child { margin-top:0; }
  }
  .card { background:#fff; border-radius:14px; padding:22px; box-shadow:0 1px 4px rgba(0,0,0,.06); margin-bottom:14px; }
  .card h2 { font-size:1rem; color:var(--green); margin-bottom:6px; }
  .card p.hint { font-size:.85rem; color:var(--muted); margin-bottom:14px; line-height:1.5; }
  label.fld { display:block; font-size:.72rem; color:var(--muted); text-transform:uppercase; letter-spacing:.4px; margin-bottom:3px; margin-top:14px; }
  input, select { width:100%; border:1.5px solid var(--border); border-radius:9px; padding:11px; font-size:1rem; outline:none; font-family:inherit; }
  input:focus, select:focus { border-color:var(--green); }
  input[type=file] { padding:8px; font-size:.85rem; }
  .duo { display:flex; gap:12px; }
  .duo > div { flex:1; }
  button { width:100%; padding:13px; background:var(--green); color:#fff; border:none; border-radius:10px; font-size:1rem; font-weight:700; cursor:pointer; margin-top:14px; }
  button:hover:not(:disabled) { background:#0c7669; }
  button:disabled { opacity:.6; cursor:not-allowed; }
  button.sec { background:#374151; margin-top:8px; }
  button.sec:hover:not(:disabled) { background:#1f2937; }
  .status { margin-top:12px; padding:11px; border-radius:10px; font-size:.88rem; display:none; }
  .ok  { background:#e8f5e9; color:#2e7d32; display:block; }
  .err { background:#fdecea; color:#c62828; display:block; }
  .info { background:#eef6ff; color:#1d4ed8; display:block; }
  .tdee { background:#eef6ff; border-radius:10px; padding:12px 14px; margin-top:14px; font-size:.9rem; color:#1d4ed8; }
  .tdee b { font-size:1.05rem; }
  .upload-row { display:flex; gap:10px; flex-wrap:wrap; align-items:center; }
  .zona-row { display:grid; grid-template-columns:54px 1fr 14px 1fr; gap:10px; align-items:center; margin-bottom:12px; }
  .zona-tag { font-weight:800; color:#fff; text-align:center; border-radius:6px; padding:6px 0; font-size:.85rem; }
  .z1{background:#9ca3af;} .z2{background:#3b82f6;} .z3{background:#10b981;}
  .z4{background:#f59e0b;} .z5{background:#ef4444;}
  .sep { text-align:center; color:var(--muted); }
  .metodo-tabs { display:flex; gap:8px; margin:10px 0 14px; }
  .tab-btn { flex:1; padding:9px; border-radius:9px; border:1.5px solid var(--border); background:#fff; font-size:.88rem; font-weight:600; cursor:pointer; color:var(--muted); transition:.15s; }
  .tab-btn.active { background:var(--green); color:#fff; border-color:var(--green); }
  .tab-btn:hover:not(.active) { border-color:var(--green); color:var(--green); }
  .metodo-desc { font-size:.85rem; color:#374151; line-height:1.6; background:#f9fafb; border-radius:9px; padding:11px 13px; border-left:3px solid var(--green); }
  .metodo-desc b { color:var(--text); }
  /* As três formas de preencher zonas moram no mesmo card — são a mesma tarefa,
     não três assuntos. Separadas por um fio, não por três cabeçalhos. */
  .metodo-bloco { border-top:1px solid var(--border); padding-top:15px; margin-top:15px; }
  .metodo-bloco:first-of-type { border-top:none; padding-top:0; margin-top:0; }
  .metodo-nome { font-size:.92rem; font-weight:700; color:var(--text); margin-bottom:8px; display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
  .metodo-sub { font-size:.83rem; color:var(--muted); line-height:1.5; }
  .garmin-badge { display:inline-flex; align-items:center; gap:5px; background:#e8f5e9; color:#2e7d32; border-radius:20px; padding:3px 10px; font-size:.75rem; font-weight:700; }
  .garmin-warn { background:#fef3c7; border:1.5px solid #fbbf24; border-radius:9px; padding:10px 13px; font-size:.84rem; color:#92400e; margin-bottom:12px; }
  .garmin-warn a { color:#b45309; font-weight:700; text-decoration:none; }
  .garmin-warn a:hover { text-decoration:underline; }
  .aca-toggle { display:flex; gap:8px; margin:12px 0 4px; }
  .aca-btn { flex:1; padding:10px; border-radius:9px; border:1.5px solid var(--border); background:#fff; font-size:.9rem; font-weight:700; cursor:pointer; color:var(--muted); transition:.15s; }
  .aca-btn.aca-active { background:var(--green); color:#fff; border-color:var(--green); }
  .aca-btn:hover:not(.aca-active) { border-color:var(--green); color:var(--green); }
  .freq-btn { padding:8px 18px; border-radius:9px; border:1.5px solid var(--border); background:#fff; font-size:.88rem; font-weight:700; cursor:pointer; color:var(--muted); transition:.15s; }
  .freq-btn.freq-active { background:var(--green); color:#fff; border-color:var(--green); }
  .freq-btn:hover:not(.freq-active) { border-color:var(--green); color:var(--green); }
  .freq-row { display:flex; gap:8px; flex-wrap:wrap; }
  .freq-row .freq-btn { width:auto; margin-top:0; }
  .dia-row { display:flex; gap:6px; flex-wrap:wrap; margin-top:6px; }
  .dia-btn { width:42px; padding:9px 0; border-radius:9px; border:1.5px solid var(--border); background:#fff; font-size:.85rem; font-weight:700; cursor:pointer; color:var(--muted); transition:.15s; margin-top:0; }
  .dia-btn.dia-active { background:var(--green); color:#fff; border-color:var(--green); }
  .dia-btn:hover:not(.dia-active) { border-color:var(--green); color:var(--green); }
  .aca-hint { font-size:.83rem; color:var(--muted); line-height:1.5; margin-bottom:14px; padding:9px 12px; background:#f9fafb; border-radius:8px; border-left:3px solid var(--green); }
  .aca-row { display:flex; align-items:center; gap:12px; padding:9px 0; border-bottom:1px solid var(--border); }
  .aca-row:last-child { border-bottom:none; }
  .aca-check { display:flex; align-items:center; gap:9px; flex:1; font-size:.92rem; cursor:pointer; }
  .aca-check input[type=checkbox] { width:18px; height:18px; accent-color:var(--green); flex-shrink:0; cursor:pointer; }
  .aca-sel { width:110px; flex-shrink:0; padding:7px 10px; font-size:.85rem; border-radius:8px; border:1.5px solid var(--border); }
  .aca-sel:disabled { opacity:.35; }
  .aca-auto-tip { margin-top:12px; padding:9px 12px; background:#eef6ff; border-radius:8px; font-size:.83rem; color:#1d4ed8; }
  .theme-toggle { display:flex; gap:8px; margin:12px 0 4px; }
  .theme-opt { flex:1; padding:10px; border-radius:9px; border:1.5px solid var(--border); background:#fff; font-size:.9rem; font-weight:700; cursor:pointer; color:var(--muted); transition:.15s; }
  .theme-opt.active { background:var(--green); color:#fff; border-color:var(--green); }
  .theme-opt:hover:not(.active) { border-color:var(--green); color:var(--green); }
  /* ── Dark theme ── */
  [data-theme="dark"] { --bg:#111827; --card:#1f2937; --text:#e5e7eb; --muted:#9ca3af; --border:#374151; --green:#1db39e; }
  [data-theme="dark"] body { background:var(--bg); color:var(--text); }
  [data-theme="dark"] .card { background:var(--card); }
  [data-theme="dark"] input,
  [data-theme="dark"] select { background:#111827; color:var(--text); border-color:var(--border); }
  [data-theme="dark"] .theme-opt { background:#1f2937; color:var(--text); border-color:var(--border); }
  [data-theme="dark"] .tdee { background:#1a2a40; color:#93c5fd; }
  [data-theme="dark"] .metodo-desc { background:#111827; color:var(--text); border-left-color:var(--green); }
  [data-theme="dark"] .metodo-desc b { color:var(--text); }
  [data-theme="dark"] .tab-btn { background:#1f2937; color:var(--muted); border-color:var(--border); }
  [data-theme="dark"] .tab-btn.active { background:var(--green); color:#fff; border-color:var(--green); }
  [data-theme="dark"] .tab-btn:hover:not(.active) { border-color:var(--green); color:var(--green); }
  [data-theme="dark"] .aca-btn { background:#1f2937; color:var(--text); border-color:var(--border); }
  [data-theme="dark"] .freq-btn { background:#1f2937; color:var(--text); border-color:var(--border); }
  [data-theme="dark"] .dia-btn { background:#1f2937; color:var(--text); border-color:var(--border); }
  /* O estado ativo precisa de override no escuro: as regras acima têm a mesma
     especificidade e vêm depois, então engoliam o verde do botão selecionado. */
  [data-theme="dark"] .aca-btn.aca-active,
  [data-theme="dark"] .freq-btn.freq-active,
  [data-theme="dark"] .dia-btn.dia-active,
  [data-theme="dark"] .theme-opt.active { background:var(--green); color:#fff; border-color:var(--green); }
  [data-theme="dark"] .aca-hint { background:#111827; border-left-color:var(--green); color:var(--muted); }
  [data-theme="dark"] .aca-auto-tip { background:#1a2a40; color:#93c5fd; }
  [data-theme="dark"] .aca-row { border-bottom-color:var(--border); }
  [data-theme="dark"] .aca-sel { background:#111827; color:var(--text); border-color:var(--border); }
  [data-theme="dark"] .garmin-warn { background:#2a1900; border-color:#7c3a00; color:#fbbf24; }
  [data-theme="dark"] .garmin-warn a { color:#fbbf24; }
  [data-theme="dark"] .garmin-badge { background:#0d2020; color:#6ee7b7; }
  [data-theme="dark"] .zona-row input { background:#111827; color:var(--text); border-color:var(--border); }
  [data-theme="dark"] #desc-objetivo { background:#111827; color:#86efac; }
  [data-theme="dark"] nav { background:var(--green); }
</style>
  <script>(function(){var t=localStorage.getItem('mtb-tema')||'__TEMA__';document.documentElement.setAttribute('data-theme',t)})();</script>
</head>
<body>
<nav>
  <span style="font-size:1.3rem">👤</span>
  <span class="logo">MTB Nutrition</span>
  <a href="/portal/">← Voltar ao portal</a>
</nav>
<main>
  <h1>Meu perfil</h1>
  <p class="sub">À esquerda, quem você é e como você treina. À direita, os números que a IA usa para prescrever.</p>

  <div class="cols">
  <div class="col">

  <!-- ── Dados pessoais ── -->
  <div class="section-title">👤 Seus dados</div>
  <div class="card">
    <form id="form" onsubmit="salvarPerfil(event)">
      <div class="duo">
        <div>
          <label class="fld">Peso (kg)</label>
          <input id="peso_kg" type="number" step="0.1" min="30" max="200" value="{{PESO}}" required>
        </div>
        <div>
          <label class="fld">Altura (cm)</label>
          <input id="altura_cm" type="number" min="100" max="250" value="{{ALTURA}}" required>
        </div>
      </div>
      <div class="duo">
        <div>
          <label class="fld">Idade</label>
          <input id="idade" type="number" min="10" max="100" value="{{IDADE}}" required>
        </div>
        <div>
          <label class="fld">Sexo</label>
          <select id="sexo">
            <option value="M" {{SEXO_M}}>Masculino</option>
            <option value="F" {{SEXO_F}}>Feminino</option>
          </select>
        </div>
      </div>
      <div class="tdee" id="tdee"></div>
      <label class="fld" style="margin-top:18px">Objetivo de treinamento</label>
      <select id="objetivo" onchange="atualizarDescObjetivo()">
        <option value="performance_mtb" {{OBJ_performance_mtb}}>Performance MTB geral</option>
        <option value="aumentar_potencia" {{OBJ_aumentar_potencia}}>Aumentar potência / FTP</option>
        <option value="base_aerobica" {{OBJ_base_aerobica}}>Construir base aeróbica</option>
        <option value="manter_performance" {{OBJ_manter_performance}}>Manter performance</option>
        <option value="emagrecimento" {{OBJ_emagrecimento}}>Emagrecer</option>
      </select>
      <div id="desc-objetivo" style="margin-top:10px;padding:12px 14px;border-radius:10px;background:#f0f9f8;font-size:.88rem;color:#065f46;line-height:1.5;"></div>
      <button type="submit" id="btn-perfil">Salvar perfil</button>
      <div id="st-perfil" class="status"></div>
    </form>
  </div>

  <!-- ── Disponibilidade para pedalar ── -->
  <div class="section-title">🚴 Disponibilidade para treinar</div>
  <div class="card">
    <h2>📅 Quantas vezes por semana você consegue pedalar?</h2>
    <p class="hint">É a partir daqui que a IA monta a sua semana. Prefira ser realista: um plano de 6 dias
      que você só cumpre em 3 atrapalha mais do que ajuda.</p>
    <div class="freq-row" id="bike-freq-row"></div>
    <label class="fld" style="margin-top:18px">Em quais dias?</label>
    <p class="aca-hint" style="margin-top:6px">Já deixamos os dias mais bem distribuídos marcados. Se os seus
      são outros, é só clicar e trocar — a IA respeita exatamente o que estiver marcado aqui.</p>
    <div class="dia-row" id="bike-dias-row"></div>
    <div class="aca-auto-tip" id="bike-resumo"></div>

    <label class="fld" style="margin-top:22px">Meta de horas por semana <span style="font-weight:400;color:#6b7280">(opcional)</span></label>
    <p class="aca-hint" style="margin-top:6px">Se você tem um volume que quer bater toda semana, informe aqui e a IA
      passa a montar as semanas somando essas horas — sem você precisar repetir isso no chat.
      Conta tudo que for planejado (pedal + academia). <b>Deixe em branco e a IA decide o volume</b>
      pela sua evolução, como faz hoje.</p>
    <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      <input id="volume_semanal_h" type="number" min="1" max="40" step="0.5"
             placeholder="ex: 10" style="max-width:150px" value="{{VOLUME_SEMANAL_H}}"
             oninput="renderVolumeResumo()">
      <span style="color:#6b7280;font-size:.9rem">horas por semana</span>
      <button type="button" class="freq-btn" onclick="limparVolume()">IA decide</button>
    </div>
    <div class="aca-auto-tip" id="volume-resumo" style="margin-top:10px"></div>

    <button type="button" id="btn-bike" onclick="salvarBike()">Salvar dias de treino</button>
    <div id="st-bike" class="status"></div>
  </div>

  <!-- ── Academia ── -->
  <div class="section-title">🏋️ Academia / Musculação</div>
  <div class="card">
    <h2>🏋️ Você treina na academia?</h2>
    <p class="hint">Configure seus dias e períodos disponíveis. A IA vai integrar musculação e bike para maximizar sua evolução — priorizando os horários que você informar.</p>
    <div class="aca-toggle">
      <button type="button" id="aca-sim" class="aca-btn" onclick="setAcademia(true)">Sim, treino</button>
      <button type="button" id="aca-nao" class="aca-btn" onclick="setAcademia(false)">Não treino</button>
    </div>
    <div id="aca-dias">
      <p class="aca-hint">Marque os dias e períodos disponíveis. Se não marcar nenhum dia, a IA escolhe automaticamente os melhores momentos da semana.</p>
      <div id="aca-grid"></div>
      <div class="aca-auto-tip" id="aca-auto-msg" style="display:none">
        💡 Nenhum dia selecionado — a IA vai definir automaticamente os melhores dias para academia com base na sua programação de bike.
      </div>
    </div>
    <div style="margin-top:16px">
      <label class="fld" style="margin-bottom:8px;display:block">Quantas vezes por semana?</label>
      <div style="display:flex;gap:8px">
        <button type="button" class="freq-btn" id="freq-0" onclick="setFreq(0)">IA decide</button>
        <button type="button" class="freq-btn" id="freq-1" onclick="setFreq(1)">1x</button>
        <button type="button" class="freq-btn" id="freq-2" onclick="setFreq(2)">2x</button>
      </div>
    </div>
    <div style="margin-top:18px">
      <label class="fld" for="academia_nivel" style="margin-bottom:6px;display:block">Qual é o seu nível na academia?</label>
      <p class="aca-hint" style="margin-top:0">Define a carga com que a IA começa. Não adianta ela sugerir
        50 kg de agachamento para quem nunca pisou numa academia — e nem 10 kg para quem já treina há anos.
        A partir da segunda sessão a referência passa a ser a carga que <b>você registrar</b> no card do treino.</p>
      <select id="academia_nivel" style="width:100%">
        <option value="nunca">Nunca treinei musculação</option>
        <option value="iniciante">Iniciante — menos de 6 meses, ou voltando depois de parado</option>
        <option value="intermediario">Intermediário — mais de 6 meses, domino os exercícios</option>
        <option value="avancado">Avançado — anos de treino, técnica sólida</option>
      </select>
    </div>
    <button type="button" id="btn-academia" onclick="salvarAcademia()" style="margin-top:18px">Salvar configuração de academia</button>
    <div id="st-academia" class="status"></div>
  </div>

  <!-- ── Metas calóricas (nutricionista) ── -->
  <div class="section-title">🍽️ Metas calóricas</div>
  <div class="card">
    <h2>📋 Dados da nutricionista</h2>
    <p class="hint">Preencha os valores definidos pela sua nutricionista. Quando preenchidos, substituem o cálculo automático de Mifflin-St Jeor.</p>
    <form id="form-nutri" onsubmit="salvarNutri(event)">
      <div class="duo">
        <div>
          <label class="fld">Basal metabólico (kcal/dia)</label>
          <input id="basal_metabolico" type="number" min="1000" max="4000" step="1" placeholder="ex: 1922" value="{{BASAL_METABOLICO}}">
        </div>
        <div>
          <label class="fld">Meta calórica diária (kcal/dia)</label>
          <input id="meta_calorica_diaria" type="number" min="1000" max="4000" step="1" placeholder="ex: 1800" value="{{META_CALORICA}}">
        </div>
      </div>
      <p style="font-size:.82rem;color:#6b7280;margin-top:10px;line-height:1.5">
        A <b>meta calórica diária</b> é usada como base nos cardápios. O gasto do treino é somado por cima automaticamente em dias de treino.
      </p>
      <button type="submit" id="btn-nutri">Salvar metas</button>
      <div id="st-nutri" class="status"></div>
    </form>
  </div>

  </div>
  <div class="col">

  <!-- ── Zonas de FC ── -->
  <div class="section-title">❤️ Zonas de frequência cardíaca</div>

  <div class="card">
    <h2>📿 Você usa cinta cardíaca?</h2>
    <p class="hint">Sem cinta, a FC gravada pelo relógio é imprecisa (ou nem existe) e a nota do treino sai injusta.
      Marcando <b>Não uso</b>, todo treino passa a ser avaliado sem FC — a nota vem de potência, volume e cadência.
      Para um treino isolado em que a cinta falhou (bateria fraca, cinta solta), use o botão
      <b>“FC não confiável”</b> no modal de avaliação do treino — ou peça no chat.</p>
    <div class="aca-toggle">
      <button type="button" id="cinta-sim" class="aca-btn" onclick="setCinta(true)">Uso cinta</button>
      <button type="button" id="cinta-nao" class="aca-btn" onclick="setCinta(false)">Não uso cinta</button>
    </div>
    <label class="aca-check" style="margin-top:12px">
      <input type="checkbox" id="cinta-reav" checked>
      <span>Reavaliar também os treinos dos últimos 14 dias</span>
    </label>
    <button type="button" id="btn-cinta" onclick="salvarCinta()">Salvar</button>
    <div id="st-cinta" class="status"></div>
  </div>

  <div class="card">
    <h2>🎯 Como preencher suas zonas</h2>
    <p class="hint">Três caminhos para os mesmos números — use o que for mais fácil pra você.
      Dá para editar tudo à mão depois, no card abaixo.</p>

    <div class="metodo-bloco">
      <p class="metodo-nome">1. Calcular a partir da sua FC</p>
      <div class="metodo-tabs">
        <button class="tab-btn" id="tab-fcmax" onclick="setMetodo('fcmax')">% FC Máxima</button>
        <button class="tab-btn" id="tab-ll" onclick="setMetodo('ll')">% Limiar Lático (LL)</button>
      </div>
      <div id="desc-fcmax" class="metodo-desc">
        <b>Simples e popular</b> — o maior batimento que seu coração atinge. Estimativa rápida:
        <b>220 − sua idade</b>. Para medir de verdade, faça um sprint de 3 min no limite e anote a FC mais alta.
      </div>
      <div id="desc-ll" class="metodo-desc" style="display:none">
        <b>Mais preciso</b> — o ponto em que você fica ofegante e não segura mais o ritmo.
        Pedale forte e constante por 30 min e anote a FC média dos <em>últimos 20 min</em>.
        Não sabe? Estime como <b>90% da FC máxima</b>.
      </div>
      <div class="duo" style="margin-top:12px">
        <div>
          <label class="fld" style="margin-top:0">FC Máxima (bpm)</label>
          <input type="number" id="fc_max" min="100" max="230" placeholder="ex: 185">
        </div>
        <div id="ll-field" style="display:none">
          <label class="fld" style="margin-top:0">Limiar Lático (bpm)</label>
          <input type="number" id="limiar" min="100" max="210" placeholder="ex: 165">
        </div>
      </div>
      <button class="sec" onclick="calcularZonasAuto()" style="margin-top:12px">⚡ Calcular zonas</button>
      <div id="st-calc" class="status"></div>
    </div>

    <div class="metodo-bloco">
      <p class="metodo-nome">2. Importar do Garmin
        <span id="garmin-badge" class="garmin-badge" style="display:none">✓ Conectado</span>
      </p>
      <p class="metodo-sub">As zonas oficiais do seu perfil de ciclismo, direto da conta — sem print, sem IA.</p>
      <div id="garmin-warn" class="garmin-warn" style="display:none">
        ⚠️ Garmin não conectado. <a href="/workout/integracao">Conectar agora →</a>
      </div>
      <button class="sec" id="btnGarmin" onclick="importarGarmin()" style="margin-top:10px">📥 Importar zonas do Garmin</button>
      <div id="stGarmin" class="status"></div>
    </div>

    <div class="metodo-bloco">
      <p class="metodo-nome">3. Ler de um print</p>
      <p class="metodo-sub">Tire um print da tela de zonas no app/relógio Garmin — a IA preenche os campos.</p>
      <div class="upload-row" style="margin-top:10px">
        <input type="file" id="img" accept="image/*">
        <button class="sec" id="btnLer" style="width:auto;padding:11px 16px;margin-top:0" onclick="lerImagem()">🤖 Ler zonas</button>
      </div>
      <div id="stImg" class="status"></div>
    </div>
  </div>

  <div class="card">
    <h2>✏️ Zonas (bpm)</h2>
    <p class="hint">Min e max de cada zona. Edite manualmente a qualquer momento.</p>
    <div id="zonas"></div>
    <button id="btnSalvarZonas" onclick="salvarZonas()">💾 Salvar zonas</button>
    <div id="st-zonas" class="status"></div>
  </div>

  <!-- ── Potência ── -->
  <div class="section-title">⚡ Potência (watts)</div>
  <div class="card">
    <h2>🎯 Seu FTP</h2>
    <p class="hint">FTP = Functional Threshold Power — watts que você sustenta por ~1h. Base para calcular as 7 zonas de potência.</p>

    <div style="background:#f9fafb;border-radius:9px;padding:12px 14px;margin-bottom:14px">
      <p style="font-size:.82rem;font-weight:700;color:#374151;margin-bottom:8px">📷 Importar do print do Garmin</p>
      <p style="font-size:.8rem;color:#6b7280;margin-bottom:10px">Tire um print da tela de Zonas de Potência no app Garmin Connect e envie — a IA extrai o FTP e as 7 zonas automaticamente.</p>
      <div class="upload-row">
        <input type="file" id="img-pot" accept="image/*">
        <button class="sec" id="btnLerPot" style="width:auto;padding:11px 16px;margin-top:0" onclick="lerImagemPotencia()">🤖 Ler zonas</button>
      </div>
      <div id="stImgPot" class="status"></div>
    </div>

    <div style="display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap;margin-bottom:14px">
      <div>
        <label style="font-size:.8rem;font-weight:600;display:block;margin-bottom:4px">FTP (watts)</label>
        <input type="number" id="ftp_val" min="50" max="700" step="1" placeholder="ex: 290" style="width:110px;padding:9px 10px;border:1.5px solid #ddd;border-radius:7px;font-size:1rem">
      </div>
      <div>
        <label style="font-size:.8rem;font-weight:600;display:block;margin-bottom:4px">Usar potência em</label>
        <select id="ftp_modo" style="padding:9px 10px;border:1.5px solid #ddd;border-radius:7px;font-size:.92rem">
          <option value="indoor">🏠 Só indoor (rolo) — treinos de qualidade</option>
          <option value="sempre">🚵 Sempre — tenho medidor na bike</option>
          <option value="ambos">⚡❤️ Watts e FC juntos — escolho na hora do treino</option>
          <option value="nunca">❌ Nunca — só FC nos treinos</option>
        </select>
      </div>
      <button id="btnSalvarFTP" onclick="salvarFTP()" style="white-space:nowrap">💾 Salvar FTP</button>
    </div>
    <p class="hint" style="margin-top:-4px">Em <b>Watts e FC juntos</b> o treino vai pro Garmin com as duas faixas no mesmo passo — o relógio mostra os watts e os bpm lado a lado e você segue a métrica que tiver naquele dia. O alerta de "fora do alvo" acompanha os watts nos dias de rolo e a FC nos dias marcados como outdoor.</p>
    <div id="st-ftp" class="status"></div>
    <div id="zonas-pot-preview" style="display:none;margin-top:12px">
      <p style="font-size:.78rem;font-weight:600;color:#555;margin-bottom:6px">ZONAS DE POTÊNCIA CALCULADAS</p>
      <div id="zonas-pot-lista"></div>
    </div>
  </div>

  <!-- ── Aparência ── -->
  <div class="section-title">🎨 Aparência</div>
  <div class="card">
    <h2>🌗 Tema do portal</h2>
    <p class="hint">Escolha entre o tema claro ou escuro. A preferência fica salva no dispositivo.</p>
    <div class="theme-toggle">
      <button type="button" id="tema-claro" class="theme-opt" onclick="setTema('light')">☀️ Claro</button>
      <button type="button" id="tema-escuro" class="theme-opt" onclick="setTema('dark')">🌙 Escuro</button>
    </div>
  </div>

  </div>
  </div>
</main>
<script>
// ── Perfil ──
const _OBJ_DESC = {
  performance_mtb: '🚵 Modelo polarizado: até 2 sessões duras por semana (VO2max + Tiros), dias fáceis em Z2 puro. A IA maximiza seu pico de performance para MTB.',
  aumentar_potencia: '⚡ Foco em sessões de limiar e VO2max para elevar FTP. A IA prioriza qualidade sobre quantidade e garante recuperação entre os dias duros.',
  base_aerobica: '🟢 Muito Z2, longões de fim de semana, sem sessões duras. A IA constrói sua base aeróbica progressivamente — essencial antes de uma temporada de provas.',
  manter_performance: '⚖️ Equilíbrio entre volume e intensidade. A IA mantém o padrão atual sem sobrecarregar nem reduzir demais.',
  emagrecimento: '🔥 Mais volume em Z2 (alto gasto calórico, baixo cortisol), 1 sessão dura por semana para preservar músculo. A IA orienta treino e nutrição para déficit calórico saudável.',
};
function atualizarDescObjetivo(){
  const v = document.getElementById('objetivo').value;
  document.getElementById('desc-objetivo').textContent = _OBJ_DESC[v] || '';
}
atualizarDescObjetivo();

function calcTDEE(){
  const peso=+document.getElementById('peso_kg').value, alt=+document.getElementById('altura_cm').value;
  const idade=+document.getElementById('idade').value, sexo=document.getElementById('sexo').value;
  const el=document.getElementById('tdee');
  if(!peso||!alt||!idade){ el.textContent='Preencha peso, altura e idade para ver a estimativa.'; return; }
  const bmr = 10*peso + 6.25*alt - 5*idade + (sexo==='M'?5:-161);
  const basal = Math.round(bmr*1.2);
  el.innerHTML = `Gasto basal estimado (sem treino): <b>${basal} kcal/dia</b>.<br>O gasto do treino é somado por cima, dia a dia.`;
}
['peso_kg','altura_cm','idade','sexo'].forEach(id=>document.getElementById(id).addEventListener('input',calcTDEE));
calcTDEE();

async function salvarPerfil(ev){
  ev.preventDefault();
  const st=document.getElementById('st-perfil'), btn=document.getElementById('btn-perfil');
  btn.disabled=true; btn.textContent='Salvando…';
  const body=new URLSearchParams({
    idade:document.getElementById('idade').value,
    peso_kg:document.getElementById('peso_kg').value,
    altura_cm:document.getElementById('altura_cm').value,
    sexo:document.getElementById('sexo').value,
    objetivo:document.getElementById('objetivo').value,
  });
  try{
    const r=await fetch('/workout/perfil',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body});
    if(!r.ok) throw new Error('Erro ao salvar');
    st.className='status ok'; st.textContent='✅ Perfil salvo!';
  }catch(e){ st.className='status err'; st.textContent='❌ '+e.message; }
  finally{ btn.disabled=false; btn.textContent='Salvar perfil'; }
}

async function salvarNutri(ev){
  ev.preventDefault();
  const st=document.getElementById('st-nutri'), btn=document.getElementById('btn-nutri');
  btn.disabled=true; btn.textContent='Salvando…';
  // envia também os campos mínimos obrigatórios do endpoint /workout/perfil
  const body=new URLSearchParams({
    idade:document.getElementById('idade').value||'0',
    peso_kg:document.getElementById('peso_kg').value||'0',
    altura_cm:document.getElementById('altura_cm').value||'0',
    sexo:document.getElementById('sexo').value,
    objetivo:document.getElementById('objetivo').value,
    basal_metabolico:document.getElementById('basal_metabolico').value,
    meta_calorica_diaria:document.getElementById('meta_calorica_diaria').value,
  });
  try{
    const r=await fetch('/workout/perfil',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body});
    if(!r.ok) throw new Error('Erro ao salvar');
    st.className='status ok'; st.textContent='✅ Metas calóricas salvas!';
  }catch(e){ st.className='status err'; st.textContent='❌ '+e.message; }
  finally{ btn.disabled=false; btn.textContent='Salvar metas'; }
}

// ── Dias de treino (bike) ──
const _DIAS_CURTOS = ['Seg','Ter','Qua','Qui','Sex','Sáb','Dom'];
// Espelha _DIAS_POR_FREQUENCIA do gerador: espaça os dias e pega o fim de semana
// cedo (é onde cabe o longão).
const _DIAS_POR_FREQ = {1:[5], 2:[2,5], 3:[1,3,5], 4:[1,3,5,6], 5:[1,2,3,5,6], 6:[0,1,2,3,4,5], 7:[0,1,2,3,4,5,6]};
let _bikeDias = {{BIKE_DIAS_JSON}};
let _bikeFreq = parseInt('{{BIKE_FREQ}}') || 0;
// Quem nunca configurou vê o que o gerador já usa hoje: seg–sáb.
if (!_bikeDias.length) _bikeDias = (_DIAS_POR_FREQ[_bikeFreq] || _DIAS_POR_FREQ[6]).slice();
_bikeFreq = _bikeDias.length;

function renderBike() {
  const fr = document.getElementById('bike-freq-row');
  fr.innerHTML = '';
  for (let n = 1; n <= 7; n++) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'freq-btn' + (n === _bikeFreq ? ' freq-active' : '');
    b.textContent = n + 'x';
    b.onclick = () => setBikeFreq(n);
    fr.appendChild(b);
  }
  const dr = document.getElementById('bike-dias-row');
  dr.innerHTML = '';
  for (let d = 0; d < 7; d++) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'dia-btn' + (_bikeDias.includes(d) ? ' dia-active' : '');
    b.textContent = _DIAS_CURTOS[d];
    b.onclick = () => toggleBikeDia(d);
    dr.appendChild(b);
  }
  const resumo = document.getElementById('bike-resumo');
  resumo.textContent = _bikeDias.length
    ? `🚴 ${_bikeDias.length}x por semana: ${_bikeDias.map(d => _DIAS_CURTOS[d]).join(', ')}.`
    : '⚠️ Marque pelo menos um dia — sem dia de treino não há o que planejar.';
  renderVolumeResumo();
}

function renderVolumeResumo() {
  const el = document.getElementById('volume-resumo');
  if (!el) return;
  const h = parseFloat(String(document.getElementById('volume_semanal_h').value).replace(',', '.'));
  if (!h || h < 1 || h > 40) {
    el.textContent = '🤖 Sem meta definida — a IA escolhe o volume de cada semana pela sua evolução.';
    return;
  }
  const total = Math.round(h * 60);
  const dias = _bikeDias.length || 1;
  el.textContent = `🎯 Meta de ${total} min por semana (~${Math.round(total / dias)} min por dia de treino em ${dias} dia(s)).`;
}

function limparVolume() {
  document.getElementById('volume_semanal_h').value = '';
  renderVolumeResumo();
}

function setBikeFreq(n) {
  _bikeFreq = n;
  _bikeDias = (_DIAS_POR_FREQ[n] || []).slice();
  renderBike();
}

function toggleBikeDia(d) {
  _bikeDias = _bikeDias.includes(d)
    ? _bikeDias.filter(x => x !== d)
    : _bikeDias.concat(d).sort((a, b) => a - b);
  _bikeFreq = _bikeDias.length;
  renderBike();
}

async function salvarBike() {
  const st = document.getElementById('st-bike'), btn = document.getElementById('btn-bike');
  if (!_bikeDias.length) {
    st.className = 'status err'; st.textContent = '⚠️ Marque pelo menos um dia de treino.';
    return;
  }
  btn.disabled = true; btn.textContent = 'Salvando…';
  const body = new URLSearchParams({
    idade: document.getElementById('idade').value || '0',
    peso_kg: document.getElementById('peso_kg').value || '0',
    altura_cm: document.getElementById('altura_cm').value || '0',
    sexo: document.getElementById('sexo').value,
    objetivo: document.getElementById('objetivo').value,
    bike_freq: String(_bikeFreq),
    bike_dias: _bikeDias.join(','),
    volume_semanal_h: document.getElementById('volume_semanal_h').value || '',
  });
  try {
    const r = await fetch('/workout/perfil', {method:'POST', headers:{'Content-Type':'application/x-www-form-urlencoded'}, body});
    if (!r.ok) throw new Error('Erro ao salvar');
    const h = parseFloat(String(document.getElementById('volume_semanal_h').value).replace(',', '.'));
    st.className = 'status ok';
    st.textContent = (h >= 1 && h <= 40)
      ? `✅ Salvo! A IA vai montar as próximas semanas com ${Math.round(h * 60)} min no total.`
      : '✅ Salvo! A IA usa esses dias na próxima semana que gerar.';
  } catch(e) { st.className = 'status err'; st.textContent = '❌ ' + e.message; }
  finally { btn.disabled = false; btn.textContent = 'Salvar dias de treino'; }
}
renderBike();

// ── Zonas de FC ──
const CORES = ['z1','z2','z3','z4','z5'];
const GARMIN_EMAIL = '{{GARMIN_EMAIL}}';
let _metodo = '{{METODO_ZONAS}}' || 'fcmax';

function configurarGarmin() {
  const badge = document.getElementById('garmin-badge');
  const warn = document.getElementById('garmin-warn');
  const btn = document.getElementById('btnGarmin');
  if (GARMIN_EMAIL) {
    badge.textContent = '✓ ' + GARMIN_EMAIL;
    badge.style.display = '';
    btn.textContent = '🔄 Reimportar zonas do Garmin';
  } else {
    warn.style.display = '';
    btn.disabled = true;
  }
}
configurarGarmin();

function setMetodo(m) {
  _metodo = m;
  document.getElementById('tab-fcmax').classList.toggle('active', m === 'fcmax');
  document.getElementById('tab-ll').classList.toggle('active', m === 'll');
  document.getElementById('desc-fcmax').style.display = m === 'fcmax' ? '' : 'none';
  document.getElementById('desc-ll').style.display = m === 'll' ? '' : 'none';
  document.getElementById('ll-field').style.display = m === 'll' ? '' : 'none';
}
setMetodo(_metodo);

function calcularZonasAuto() {
  const fc = Number(document.getElementById('fc_max').value);
  const st = document.getElementById('st-calc');
  if (_metodo === 'fcmax') {
    if (!fc || fc < 100 || fc > 230) { st.className='status err'; st.textContent='⚠️ Informe a FC Máxima (100–230 bpm).'; return; }
    const pcts = [[0.64,0.76],[0.77,0.85],[0.86,0.89],[0.90,0.94],[0.95,1.00]];
    renderZonas(pcts.map(([mn,mx],i) => ({zona:i+1,min:Math.round(fc*mn),max:i===4?fc:Math.round(fc*mx)})));
    st.className='status ok'; st.textContent='✅ Calculado por % FC Máxima. Revise e salve.';
  } else {
    const lim = Number(document.getElementById('limiar').value);
    if (!lim || lim < 100 || lim > 210) { st.className='status err'; st.textContent='⚠️ Informe o Limiar Lático (100–210 bpm).'; return; }
    const pcts = [[0.65,0.84],[0.85,0.89],[0.90,0.94],[0.95,0.99],[1.00,1.05]];
    renderZonas(pcts.map(([mn,mx],i) => ({zona:i+1,min:Math.round(lim*mn),max:i===4?(fc&&fc>lim?fc:Math.round(lim*mx)):Math.round(lim*mx)})));
    st.className='status ok'; st.textContent='✅ Calculado por % Limiar Lático. Revise e salve.';
  }
}

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
function coletarZonas() {
  const zonas = [];
  for (let i = 1; i <= 5; i++) {
    zonas.push({
      zona: i,
      min: Number(document.getElementById(`z${i}_min`).value),
      max: Number(document.getElementById(`z${i}_max`).value),
    });
  }
  const fc = document.getElementById('fc_max').value;
  const limEl = document.getElementById('limiar');
  const lim = limEl ? limEl.value : '';
  return { fc_max: fc ? Number(fc) : null, limiar: lim ? Number(lim) : null, metodo: _metodo, zonas };
}
function aplicarZonas(d) {
  renderZonas(d.zonas);
  if (d.fc_max != null) document.getElementById('fc_max').value = d.fc_max;
  const limEl = document.getElementById('limiar');
  if (limEl && d.limiar != null) limEl.value = d.limiar;
  if (d.metodo) setMetodo(d.metodo);
}
async function carregarZonas() {
  try {
    const r = await fetch('/workout/zonas/dados');
    const d = await r.json();
    aplicarZonas(d);
    if (d.potencia) aplicarFTP(d.potencia);
  } catch(e) { renderZonas([]); }
}

const _CORES_POT = ['#90a4ae','#42a5f5','#66bb6a','#ffa726','#ef5350','#ab47bc','#37474f'];
function aplicarFTP(zp) {
  if (!zp) return;
  document.getElementById('ftp_val').value = zp.ftp || '';
  document.getElementById('ftp_modo').value = zp.potencia_modo || 'indoor';
  renderZonasPot(zp.zonas || [], zp.ftp);
}
function renderZonasPot(zonas, ftp) {
  const preview = document.getElementById('zonas-pot-preview');
  const lista = document.getElementById('zonas-pot-lista');
  if (!zonas.length) { preview.style.display='none'; return; }
  preview.style.display = '';
  lista.innerHTML = zonas.map((z,i) => {
    const maxStr = z.max >= 9000 ? '∞' : z.max+'W';
    const pctMin = ftp ? Math.round(z.min/ftp*100) : '';
    const pctMax = ftp && z.max < 9000 ? Math.round(z.max/ftp*100) : '';
    const pct = pctMin && pctMax ? ` (${pctMin}–${pctMax}% FTP)` : pctMin ? ` (>${pctMin}% FTP)` : '';
    return `<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;font-size:.82rem">
      <span style="width:24px;height:14px;border-radius:3px;background:${_CORES_POT[i]};display:inline-block"></span>
      <b>Z${z.zona}</b>
      <span style="color:#555">${z.nome}</span>
      <span style="margin-left:auto;font-weight:600">${z.min}–${maxStr}${pct}</span>
    </div>`;
  }).join('');
}
async function salvarFTP() {
  const btn=document.getElementById('btnSalvarFTP'), st=document.getElementById('st-ftp');
  const ftp = Number(document.getElementById('ftp_val').value);
  const modo = document.getElementById('ftp_modo').value;
  if (!ftp) { st.className='status err'; st.textContent='⚠️ Informe o FTP em watts.'; return; }
  btn.disabled=true; btn.textContent='Salvando...'; st.className='status';
  try {
    const r = await fetch('/workout/zonas/ftp', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ftp, modo})});
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || 'Erro');
    renderZonasPot(d.zonas || [], d.ftp);
    st.className='status ok'; st.textContent=`✅ FTP ${d.ftp}W salvo! Zonas calculadas.`;
  } catch(e) { st.className='status err'; st.textContent='❌ '+e.message; }
  finally { btn.disabled=false; btn.textContent='💾 Salvar FTP'; }
}
async function importarGarmin() {
  const btn=document.getElementById('btnGarmin'), st=document.getElementById('stGarmin');
  btn.disabled=true; btn.textContent='Importando...'; st.className='status info'; st.textContent='📡 Lendo zonas do Garmin...';
  try {
    const r = await fetch('/workout/zonas/importar-garmin', {method:'POST'});
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || 'Erro');
    aplicarZonas(d);
    const esporte = d.sport ? ' (perfil ' + d.sport.toLowerCase() + ')' : '';
    st.className='status ok'; st.textContent='✅ Zonas importadas do Garmin' + esporte + '! Confira e clique em Salvar.';
  } catch(e) { st.className='status err'; st.textContent='❌ ' + e.message; }
  finally { btn.disabled=false; btn.textContent='📥 Importar zonas do Garmin'; }
}
async function lerImagem() {
  const inp=document.getElementById('img'), st=document.getElementById('stImg'), btn=document.getElementById('btnLer');
  if (!inp.files.length) { st.className='status err'; st.textContent='⚠️ Escolha uma imagem primeiro.'; return; }
  btn.disabled=true; btn.textContent='Lendo...'; st.className='status info'; st.textContent='🤖 Analisando a imagem...';
  try {
    const fd = new FormData(); fd.append('imagem', inp.files[0]);
    const r = await fetch('/workout/zonas/extrair', {method:'POST', body: fd});
    const d = await r.json();
    if (!r.ok) { const err = new Error(d.detail || 'Erro'); err.cota = (r.status === 429); throw err; }
    aplicarZonas(d);
    st.className='status ok'; st.textContent='✅ Zonas preenchidas! Confira e clique em Salvar.';
  } catch(e) {
    if (e.cota) { st.className='status info'; st.textContent='⏳ ' + e.message; }
    else { st.className='status err'; st.textContent='❌ ' + e.message; }
  }
  finally { btn.disabled=false; btn.textContent='🤖 Ler zonas'; }
}
async function lerImagemPotencia() {
  const inp=document.getElementById('img-pot'), st=document.getElementById('stImgPot'), btn=document.getElementById('btnLerPot');
  if (!inp.files.length) { st.className='status err'; st.textContent='⚠️ Escolha uma imagem primeiro.'; return; }
  btn.disabled=true; btn.textContent='Lendo...'; st.className='status info'; st.textContent='🤖 Analisando as zonas de potência...';
  try {
    const fd = new FormData(); fd.append('imagem', inp.files[0]);
    const r = await fetch('/workout/zonas/extrair-potencia', {method:'POST', body: fd});
    const d = await r.json();
    if (!r.ok) { const err = new Error(d.detail || 'Erro'); err.cota = (r.status === 429); throw err; }
    if (d.ftp) document.getElementById('ftp_val').value = d.ftp;
    if (d.zonas && d.zonas.length) renderZonasPot(d.zonas, d.ftp);
    st.className='status ok'; st.textContent='✅ FTP e zonas preenchidos! Confira e clique em Salvar FTP.';
  } catch(e) {
    if (e.cota) { st.className='status info'; st.textContent='⏳ ' + e.message; }
    else { st.className='status err'; st.textContent='❌ ' + e.message; }
  }
  finally { btn.disabled=false; btn.textContent='🤖 Ler zonas'; }
}
async function salvarZonas() {
  const btn=document.getElementById('btnSalvarZonas'), st=document.getElementById('st-zonas');
  btn.disabled=true; btn.textContent='Salvando...'; st.className='status';
  try {
    const r = await fetch('/workout/zonas/salvar', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(coletarZonas())});
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || 'Erro');
    aplicarZonas(d);
    const sync = (d.garmin_sync && d.garmin_sync.ok) ? ' e sincronizadas com o Garmin 📤' : '';
    st.className='status ok'; st.textContent='✅ Zonas salvas' + sync;
  } catch(e) { st.className='status err'; st.textContent='❌ ' + e.message; }
  finally { btn.disabled=false; btn.textContent='💾 Salvar zonas'; }
}
carregarZonas();

// ── Cinta cardíaca ──
let _usaCinta = '{{USA_CINTA}}' === '1';

function setCinta(v) {
  _usaCinta = v;
  document.getElementById('cinta-sim').classList.toggle('aca-active', v);
  document.getElementById('cinta-nao').classList.toggle('aca-active', !v);
}

async function salvarCinta() {
  const btn = document.getElementById('btn-cinta'), st = document.getElementById('st-cinta');
  const dias = document.getElementById('cinta-reav').checked ? 14 : 0;
  btn.disabled = true; btn.textContent = 'Salvando…';
  st.className = 'status info'; st.textContent = dias ? '🤖 Salvando e reavaliando treinos…' : 'Salvando…';
  try {
    const r = await fetch('/workout/cinta-fc', {
      method: 'PATCH', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({usa_cinta: _usaCinta, reavaliar_dias: dias}),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || 'Erro');
    const n = (d.reavaliados || []).length;
    st.className = 'status ok';
    st.textContent = (_usaCinta ? '✅ FC voltará a contar nas avaliações.' : '✅ Seus treinos serão avaliados sem FC.')
                   + (n ? ` ${n} treino(s) recente(s) reavaliado(s).` : '');
  } catch(e) { st.className = 'status err'; st.textContent = '❌ ' + e.message; }
  finally { btn.disabled = false; btn.textContent = 'Salvar'; }
}
setCinta(_usaCinta);

// ── Academia ──
const _ACA_DIAS_NOMES =['Segunda-feira','Terça-feira','Quarta-feira','Quinta-feira','Sexta-feira','Sábado','Domingo'];
let _academiaTreina = '{{ACADEMIA_TREINA}}' === '1';
let _academiaDisp = {{ACADEMIA_DISP_JSON}};
let _academiaFreq = parseInt('{{ACADEMIA_FREQ}}') || 0;

function setAcademia(v) {
  _academiaTreina = v;
  document.getElementById('aca-sim').classList.toggle('aca-active', v);
  document.getElementById('aca-nao').classList.toggle('aca-active', !v);
  document.getElementById('aca-dias').style.display = v ? '' : 'none';
}

function setFreq(v) {
  _academiaFreq = v;
  [0, 1, 2].forEach(n => {
    document.getElementById(`freq-${n}`).classList.toggle('freq-active', n === v);
  });
}

function atualizarAcaAutoMsg() {
  const algumMarcado = Object.keys(_academiaDisp).length > 0;
  document.getElementById('aca-auto-msg').style.display = (!algumMarcado && _academiaTreina) ? '' : 'none';
}

function renderAcaGrid() {
  const grid = document.getElementById('aca-grid');
  grid.innerHTML = '';
  for (let d = 0; d < 7; d++) {
    const periodo = _academiaDisp[String(d)];
    const checked = periodo != null;
    const row = document.createElement('div');
    row.className = 'aca-row';
    row.innerHTML = `
      <label class="aca-check">
        <input type="checkbox" id="aca_ck_${d}" ${checked ? 'checked' : ''} onchange="toggleAcaDia(${d})">
        <span>${_ACA_DIAS_NOMES[d]}</span>
      </label>
      <select id="aca_per_${d}" class="aca-sel" ${checked ? '' : 'disabled'} onchange="updateAcaPer(${d})">
        <option value="manha" ${(periodo||'manha')==='manha'?'selected':''}>Manhã</option>
        <option value="tarde" ${periodo==='tarde'?'selected':''}>Tarde</option>
        <option value="noite" ${periodo==='noite'?'selected':''}>Noite</option>
      </select>`;
    grid.appendChild(row);
  }
  atualizarAcaAutoMsg();
}

function toggleAcaDia(d) {
  const ck = document.getElementById(`aca_ck_${d}`);
  const sel = document.getElementById(`aca_per_${d}`);
  sel.disabled = !ck.checked;
  if (ck.checked) {
    _academiaDisp[String(d)] = sel.value;
  } else {
    delete _academiaDisp[String(d)];
  }
  atualizarAcaAutoMsg();
}

function updateAcaPer(d) {
  const sel = document.getElementById(`aca_per_${d}`);
  _academiaDisp[String(d)] = sel.value;
}

async function salvarAcademia() {
  const btn = document.getElementById('btn-academia');
  const st = document.getElementById('st-academia');
  btn.disabled = true; btn.textContent = 'Salvando…';
  const body = new URLSearchParams();
  // inclui campos de perfil mínimos (requeridos pelo endpoint)
  body.set('idade', document.getElementById('idade').value || '0');
  body.set('peso_kg', document.getElementById('peso_kg').value || '0');
  body.set('altura_cm', document.getElementById('altura_cm').value || '0');
  body.set('sexo', document.getElementById('sexo').value);
  body.set('objetivo', document.getElementById('objetivo').value);
  body.set('treina_academia', _academiaTreina ? '1' : '0');
  body.set('academia_freq', String(_academiaFreq));
  body.set('academia_nivel', document.getElementById('academia_nivel').value);
  for (let d = 0; d < 7; d++) {
    const val = _academiaDisp[String(d)];
    body.set(`academia_dia_${d}`, val || 'none');
  }
  try {
    const r = await fetch('/workout/perfil', {method:'POST', headers:{'Content-Type':'application/x-www-form-urlencoded'}, body});
    if (!r.ok) throw new Error('Erro ao salvar');
    st.className = 'status ok'; st.textContent = '✅ Configuração de academia salva!';
  } catch(e) {
    st.className = 'status err'; st.textContent = '❌ ' + e.message;
  } finally {
    btn.disabled = false; btn.textContent = 'Salvar configuração de academia';
  }
}

setAcademia(_academiaTreina);
renderAcaGrid();
setFreq(_academiaFreq);
// Nível ainda não informado (usuário antigo) cai em iniciante — mesmo lado
// seguro que o gerador assume.
document.getElementById('academia_nivel').value = '{{ACADEMIA_NIVEL}}' || 'iniciante';

function setTema(t) {
  localStorage.setItem('mtb-tema', t);
  document.documentElement.setAttribute('data-theme', t);
  document.getElementById('tema-claro').classList.toggle('active', t === 'light');
  document.getElementById('tema-escuro').classList.toggle('active', t === 'dark');
  fetch('/workout/tema', {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({tema:t})});
}
// Inicializa botões com o tema atual
(function(){
  const t = localStorage.getItem('mtb-tema') || 'light';
  document.getElementById('tema-claro').classList.toggle('active', t === 'light');
  document.getElementById('tema-escuro').classList.toggle('active', t === 'dark');
})();
</script>
</body>
</html>"""
_PAGINA_EVOLUCAO = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Evolução — MTB Nutrition</title>
<style>
  :root { --green:#128c7e; --bg:#f0f2f5; --card:#fff; --text:#1a1a2e; --muted:#6b7280; --border:#e5e7eb; --accent:#2dd4bf; }
  [data-theme="dark"] { --bg:#0b1220; --card:#1a2536; --text:#e5e7eb; --muted:#94a3b8; --border:#2a3852; --green:#1db39e; --accent:#2dd4bf; }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; background:var(--bg); color:var(--text); }
  nav { background:var(--green); color:#fff; padding:14px 20px; display:flex; align-items:center; gap:12px; flex-wrap:wrap; }
  nav .logo { font-weight:700; font-size:1.05rem; }
  nav a { margin-left:auto; color:rgba(255,255,255,.9); text-decoration:none; font-size:.9rem; font-weight:600; white-space:nowrap; }
  main { max-width:960px; margin:0 auto; padding:26px 20px 60px; }
  h1 { font-size:1.5rem; margin-bottom:6px; }
  .sub { color:var(--muted); margin-bottom:24px; font-size:.93rem; }
  .card { background:var(--card); border:1px solid var(--border); border-radius:14px; padding:20px; margin-bottom:18px; }
  .card h2 { font-size:1rem; color:var(--green); margin-bottom:4px; }
  .card .hint { font-size:.8rem; color:var(--muted); margin-bottom:16px; line-height:1.5; }

  .tiles { display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:12px; margin-bottom:18px; }
  .tile { background:var(--card); border:1px solid var(--border); border-radius:12px; padding:14px 16px; }
  .tile .v { font-size:1.7rem; font-weight:800; line-height:1.1; }
  .tile .l { font-size:.72rem; color:var(--muted); text-transform:uppercase; letter-spacing:.5px; margin-top:3px; font-weight:700; }
  .tile .d { font-size:.75rem; color:var(--muted); margin-top:5px; }
  .up { color:#16a34a; font-weight:700; }

  .bars { display:flex; align-items:flex-end; gap:5px; height:150px; }
  .bar-col { flex:1; display:flex; flex-direction:column; justify-content:flex-end; align-items:center; height:100%; position:relative; }
  .bar { width:100%; background:linear-gradient(180deg,var(--accent),var(--green)); border-radius:5px 5px 0 0; min-height:2px; transition:filter .15s; }
  .bar.vazia { background:var(--border); }
  .bar-col:hover .bar { filter:brightness(1.15); }
  .bar-col .tip { position:absolute; bottom:calc(100% + 6px); left:50%; transform:translateX(-50%); background:#0b0b0b; color:#fff; font-size:.7rem; padding:6px 9px; border-radius:7px; white-space:nowrap; opacity:0; visibility:hidden; z-index:5; }
  .bar-col:hover .tip { opacity:1; visibility:visible; }
  .axis { display:flex; gap:5px; margin-top:7px; }
  .axis span { flex:1; text-align:center; font-size:.62rem; color:var(--muted); }

  .curva { display:grid; gap:9px; }
  .cv-linha { display:grid; grid-template-columns:64px 1fr 76px; align-items:center; gap:12px; }
  .cv-dur { font-size:.8rem; color:var(--muted); font-weight:700; text-align:right; }
  .cv-barra { height:24px; background:var(--border); border-radius:6px; overflow:hidden; }
  .cv-barra i { display:block; height:100%; background:linear-gradient(90deg,var(--green),var(--accent)); border-radius:6px; }
  .cv-w { font-size:.9rem; font-weight:800; }
  .cv-w small { display:block; font-size:.68rem; color:var(--muted); font-weight:500; }

  .vazio { text-align:center; padding:26px 16px; color:var(--muted); font-size:.9rem; line-height:1.6; }
  .vazio b { color:var(--text); }
  .btn { display:inline-block; margin-top:12px; background:var(--green); color:#fff; border:none; border-radius:9px; padding:11px 20px; font-size:.9rem; font-weight:700; cursor:pointer; text-decoration:none; }
</style>
<script>(function(){var t=localStorage.getItem('mtb-tema')||'__TEMA__';document.documentElement.setAttribute('data-theme',t)})();</script>
</head>
<body>
<nav>
  <span style="font-size:1.4rem">📈</span>
  <span class="logo">MTB Nutrition</span>
  <a href="/portal/">← Voltar ao portal</a>
</nav>
<main>
  <h1>Sua evolução</h1>
  <p class="sub">O que mudou nas últimas 12 semanas — comparando você com você mesmo.</p>
  <div id="conteudo"><p class="vazio">Carregando…</p></div>
</main>

<script>
function fmtSemana(iso) {
  const [a, m, d] = iso.split('-');
  return d + '/' + m;
}

function tileFtp(f) {
  if (f.atual) {
    const est = (f.estimado && f.estimado > f.atual)
      ? `<div class="d up">↑ ${f.estimado}W disponível na sua curva</div>`
      : (f.estimado_de ? `<div class="d">de ${f.estimado_de}</div>` : '');
    return `<div class="tile"><div class="v">${f.atual}<small style="font-size:.9rem">W</small></div>
            <div class="l">FTP</div>${est}</div>`;
  }
  return `<div class="tile"><div class="v">—</div><div class="l">FTP</div>
          <div class="d">Sem dado de potência ainda</div></div>`;
}

function render(d) {
  const el = document.getElementById('conteudo');
  const t = d.totais;

  if (!t.sessoes && !d.curva.length) {
    el.innerHTML = `<div class="card"><p class="vazio">
      Ainda não há treinos suficientes para montar sua evolução.<br>
      <b>Conecte o Garmin</b> — importamos seus últimos 90 dias e esta tela nasce cheia.
      <br><a class="btn" href="/workout/integracao">Conectar agora</a></p></div>`;
    return;
  }

  // ── Tiles
  let html = `<div class="tiles">
    ${tileFtp(d.ftp)}
    <div class="tile"><div class="v">${t.sessoes}</div><div class="l">Treinos</div>
      <div class="d">em ${t.semanas_com_treino} semana(s)</div></div>
    <div class="tile"><div class="v">${t.horas}<small style="font-size:.9rem">h</small></div>
      <div class="l">No selim</div><div class="d">${t.km} km rodados</div></div>
    <div class="tile"><div class="v">${t.tss_medio ?? '—'}</div><div class="l">Carga média</div>
      <div class="d">TSS por semana</div></div>
  </div>`;

  // ── Carga semanal
  const maxTss = Math.max(...d.semanal.map(s => s.tss), 1);
  const barras = d.semanal.map(s => {
    const h = s.tss ? Math.max(3, Math.round(100 * s.tss / maxTss)) : 2;
    const det = s.sessoes
      ? `${s.sessoes} treino(s) · ${Math.round(s.minutos/60)}h · ${s.km} km`
      : 'sem treino registrado';
    return `<div class="bar-col">
      <div class="tip"><b>${fmtSemana(s.semana)}</b> · ${s.tss} TSS<br>${det}</div>
      <div class="bar ${s.tss ? '' : 'vazia'}" style="height:${h}%"></div>
    </div>`;
  }).join('');
  html += `<div class="card">
    <h2>Carga por semana</h2>
    <p class="hint">Soma do TSS de cada semana. Uma barra baixa não é fracasso — semana de descanso também constrói.</p>
    <div class="bars">${barras}</div>
    <div class="axis">${d.semanal.map(s => `<span>${fmtSemana(s.semana)}</span>`).join('')}</div>
  </div>`;

  // ── Curva de potência
  if (d.curva.length) {
    const maxW = Math.max(...d.curva.map(c => c.watts));
    const rot = {5:'5s', 15:'15s', 60:'1min', 300:'5min', 600:'10min', 1200:'20min', 3600:'1h'};
    const linhas = d.curva.map(c => `<div class="cv-linha">
        <div class="cv-dur">${rot[c.duracao_s] || c.duracao_s + 's'}</div>
        <div class="cv-barra"><i style="width:${Math.round(100*c.watts/maxW)}%"></i></div>
        <div class="cv-w">${c.watts}W<small>${c.data ? c.data.slice(8,10)+'/'+c.data.slice(5,7) : ''}</small></div>
      </div>`).join('');
    html += `<div class="card">
      <h2>Curva de potência — 90 dias</h2>
      <p class="hint">Seu melhor esforço sustentado em cada duração. É daqui que sai o seu FTP: os 20 minutos valem 95% do que você aguenta uma hora inteira.</p>
      <div class="curva">${linhas}</div>
    </div>`;
  } else {
    html += `<div class="card"><h2>Curva de potência</h2>
      <p class="vazio">Ainda sem dados de potência. A curva aparece assim que você
      pedalar com medidor de potência (ou no rolo interativo).</p></div>`;
  }

  // ── FTP no tempo
  if (d.ftp_historico.length > 1) {
    const p = d.ftp_historico;
    const primeiro = p[0], ultimo = p[p.length - 1];
    const delta = ultimo.ftp - primeiro.ftp;
    const pct = Math.round(100 * delta / primeiro.ftp);
    html += `<div class="card">
      <h2>Seu FTP no tempo</h2>
      <p class="hint">${delta > 0
        ? `<span class="up">+${delta}W (${pct}%)</span> desde ${primeiro.data}. Isso é potência que você não tinha.`
        : `${primeiro.ftp}W → ${ultimo.ftp}W desde ${primeiro.data}.`}</p>
      <div class="curva">${p.map(x => `<div class="cv-linha">
        <div class="cv-dur">${x.data.slice(8,10)+'/'+x.data.slice(5,7)}</div>
        <div class="cv-barra"><i style="width:${Math.round(100*x.ftp/Math.max(...p.map(y=>y.ftp)))}%"></i></div>
        <div class="cv-w">${x.ftp}W<small>${x.origem === 'estimado' ? 'estimado' : 'teste'}</small></div>
      </div>`).join('')}</div>
    </div>`;
  }

  el.innerHTML = html;
}

fetch('/workout/evolucao/dados')
  .then(r => r.json())
  .then(render)
  .catch(() => {
    document.getElementById('conteudo').innerHTML =
      '<div class="card"><p class="vazio">Não consegui carregar sua evolução agora.</p></div>';
  });
</script>
</body>
</html>"""
