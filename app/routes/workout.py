import os
import shutil
import logging
from fastapi import APIRouter, HTTPException, UploadFile, File, Request, Form
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from app.models.models import Treino, TipoTreino
from app.services.mongo_service import get_db
from app.services.fit_service import analisar_fit
from app.services.ai_service import classificar_tipo_treino
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
    hoje = datetime.now().date()
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
    db = get_db()
    doc = await db.semanas.find_one(
        {"semana_inicio": semana_inicio, "user_id": request.state.user_id}, {"_id": 0})
    if not doc:
        return {"semana_inicio": semana_inicio, "objetivo": "", "treinos": []}
    return doc


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
        existing_map = {
            t["data"]: t
            for t in existing.get("treinos", [])
        }
        for i, t in enumerate(data["treinos"]):
            saved = existing_map.get(t["data"], {})
            # preserva resultado e garmin_workout_id do sync
            if saved.get("resultado") and not t.get("resultado"):
                t["resultado"] = saved["resultado"]
            if saved.get("garmin_workout_id") and not t.get("garmin_workout_id"):
                t["garmin_workout_id"] = saved["garmin_workout_id"]
            # bloqueia alteração se data >= hoje E treino ainda não foi realizado
            if t["data"] >= today_iso and not saved.get("resultado") and saved:
                data["treinos"][i] = saved

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
        descricao = t.get("descricao")
        if not descricao:
            continue
        novo_tipo = classificar_por_texto(descricao)
        if novo_tipo and novo_tipo != t.get("tipo"):
            await db.semanas.update_one(
                {"semana_inicio": semana_inicio, "user_id": user_id, "treinos.data": t["data"]},
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

    # Não sobrescreve uma semana que já tem treino real registrado.
    existing = await db.semanas.find_one(
        {"semana_inicio": semana_inicio, "user_id": user_id})
    if existing and any(
        (t.get("tipo") != "DESCANSO" and t.get("duracao_min")) or t.get("resultado")
        for t in existing.get("treinos", [])
    ):
        raise HTTPException(
            status_code=409,
            detail="Esta semana já tem treinos. Apague-os antes de gerar de novo.")

    plano = await _gerar(user_id, semana_inicio)
    doc = {
        "semana_inicio": semana_inicio,
        "user_id": user_id,
        "objetivo": plano.get("progressao", ""),
        "origem": "auto",
        "treinos": plano["treinos"],
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
    if existing:
        for t in existing.get("treinos", []):
            if t.get("garmin_workout_id"):
                existing_gids[t["data"]] = t["garmin_workout_id"]

    data = {
        "semana_inicio": body.semana_inicio,
        "user_id": user_id,
        "objetivo": body.objetivo,
        "treinos": [t.model_dump() for t in body.treinos],
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
                {"semana_inicio": body.semana_inicio, "user_id": user_id, "treinos.data": t.data},
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
        if t.get("tipo") in ("DESCANSO", "ACADEMIA") or not t.get("duracao_min"):
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
                {"semana_inicio": semana_inicio, "user_id": user_id, "treinos.data": t["data"]},
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
    """Zonas de FC atualmente configuradas."""
    from app.services.config_service import get_zonas
    return await get_zonas(request.state.user_id)


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
    return _PAGINA_ZONAS.replace("{{GARMIN_EMAIL}}", garmin_email)


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

    return _PAGINA_INTEGRACAO.replace("{{GARMIN_BLOCO}}", garmin_html)


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

    return {
        "prova": prova,
        "dias_restantes": dias,
        "semanas_restantes": semanas,
        "fase": fase,
        "fase_label": FASE_LABEL.get(fase, fase),
        "focos": itens or [],
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
async def pagina_calendario():
    return _PAGINA_CALENDARIO


_OBJETIVOS_VALIDOS = {"performance_mtb", "aumentar_potencia", "base_aerobica", "manter_performance", "emagrecimento"}

@router.get("/perfil", response_class=HTMLResponse)
async def pagina_perfil(request: Request):
    import json as _json
    from app.services.user_service import get_por_id
    u = await get_por_id(request.state.user_id) or {}
    p = u.get("perfil") or {}
    pref = u.get("preferencias") or {}
    val = lambda x: "" if x in (None, 0) else str(x)
    sexo = str(p.get("sexo") or "M").upper()
    obj = pref.get("objetivo") or "performance_mtb"
    metodo_zonas = (u.get("zonas") or {}).get("metodo") or "fcmax"
    garmin_email = str(((u.get("integracao") or {}).get("garmin") or {}).get("email") or "")
    academia = u.get("academia") or {}
    academia_treina = "1" if academia.get("treina") else "0"
    academia_disp_json = _json.dumps(academia.get("disponibilidade") or {})
    html = (_PAGINA_PERFIL
            .replace("{{IDADE}}", val(p.get("idade")))
            .replace("{{PESO}}", val(p.get("peso_kg")))
            .replace("{{ALTURA}}", val(p.get("altura_cm")))
            .replace("{{SEXO_M}}", "selected" if sexo.startswith("M") else "")
            .replace("{{SEXO_F}}", "selected" if sexo.startswith("F") else "")
            .replace("{{METODO_ZONAS}}", metodo_zonas)
            .replace("{{GARMIN_EMAIL}}", garmin_email)
            .replace("{{ACADEMIA_TREINA}}", academia_treina)
            .replace("{{ACADEMIA_DISP_JSON}}", academia_disp_json))
    for o in _OBJETIVOS_VALIDOS:
        html = html.replace(f"{{{{OBJ_{o}}}}}", "selected" if obj == o else "")
    return html


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

    await atualizar_usuario(request.state.user_id, {
        "perfil.idade": idade,
        "perfil.peso_kg": peso_kg,
        "perfil.altura_cm": altura_cm,
        "perfil.sexo": sexo,
        "preferencias.objetivo": obj,
        "academia.treina": treina_academia,
        "academia.disponibilidade": disponibilidade,
    })
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
            "user_id": user_id,
            "objetivo": "",
            "treinos": [novo_treino],
        })
    else:
        treino_existe = any(t.get("data") == data for t in doc.get("treinos", []))
        if treino_existe:
            # apenas campos com valor — preserva descricao já salva
            fields = {f"treinos.$.{k}": v for k, v in novo_treino.items() if v is not None}
            await db.semanas.update_one(
                {"semana_inicio": semana_inicio, "user_id": user_id, "treinos.data": data},
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
        {"semana_inicio": semana_inicio, "user_id": request.state.user_id, "treinos.data": data},
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
</style>
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
      setTimeout(() => location.reload(), 1200);
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
</style>
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
  .garmin-badge { display:inline-flex; align-items:center; gap:5px; background:#e8f5e9; color:#2e7d32; border-radius:20px; padding:3px 10px; font-size:.75rem; font-weight:700; }
  .garmin-warn { background:#fef3c7; border:1.5px solid #fbbf24; border-radius:9px; padding:10px 13px; font-size:.84rem; color:#92400e; margin-bottom:12px; }
  .garmin-warn a { color:#b45309; font-weight:700; text-decoration:none; }
  .garmin-warn a:hover { text-decoration:underline; }
  .aca-toggle { display:flex; gap:8px; margin:12px 0 4px; }
  .aca-btn { flex:1; padding:10px; border-radius:9px; border:1.5px solid var(--border); background:#fff; font-size:.9rem; font-weight:700; cursor:pointer; color:var(--muted); transition:.15s; }
  .aca-btn.aca-active { background:var(--green); color:#fff; border-color:var(--green); }
  .aca-btn:hover:not(.aca-active) { border-color:var(--green); color:var(--green); }
  .aca-hint { font-size:.83rem; color:var(--muted); line-height:1.5; margin-bottom:14px; padding:9px 12px; background:#f9fafb; border-radius:8px; border-left:3px solid var(--green); }
  .aca-row { display:flex; align-items:center; gap:12px; padding:9px 0; border-bottom:1px solid var(--border); }
  .aca-row:last-child { border-bottom:none; }
  .aca-check { display:flex; align-items:center; gap:9px; flex:1; font-size:.92rem; cursor:pointer; }
  .aca-check input[type=checkbox] { width:18px; height:18px; accent-color:var(--green); flex-shrink:0; cursor:pointer; }
  .aca-sel { width:110px; flex-shrink:0; padding:7px 10px; font-size:.85rem; border-radius:8px; border:1.5px solid var(--border); }
  .aca-sel:disabled { opacity:.35; }
  .aca-auto-tip { margin-top:12px; padding:9px 12px; background:#eef6ff; border-radius:8px; font-size:.83rem; color:#1d4ed8; }
</style>
</head>
<body>
<nav>
  <span style="font-size:1.3rem">👤</span>
  <span class="logo">MTB Nutrition</span>
  <a href="/portal/">← Voltar ao portal</a>
</nav>
<main>
  <h1>Meu perfil</h1>
  <p class="sub">Dados pessoais, objetivo de treino e zonas de frequência cardíaca.</p>

  <!-- ── Dados pessoais ── -->
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
    <button type="button" id="btn-academia" onclick="salvarAcademia()" style="margin-top:18px">Salvar configuração de academia</button>
    <div id="st-academia" class="status"></div>
  </div>

  <!-- ── Zonas de FC ── -->
  <div class="section-title">❤️ Zonas de frequência cardíaca</div>

  <div class="card">
    <h2>⚙️ Como calcular suas zonas?</h2>
    <p class="hint">Existem dois métodos. Não sabe qual usar? Comece pelo <b>% FC Máxima</b> — é o mais simples.</p>
    <div class="metodo-tabs">
      <button class="tab-btn" id="tab-fcmax" onclick="setMetodo('fcmax')">% FC Máxima</button>
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
    <p class="hint">Puxa as zonas oficiais do seu perfil de ciclismo direto da conta Garmin — sem print, sem IA.</p>
    <div id="garmin-warn" class="garmin-warn" style="display:none">
      ⚠️ Garmin não conectado. <a href="/workout/integracao">Conectar agora →</a>
    </div>
    <button id="btnGarmin" onclick="importarGarmin()">📥 Importar zonas do Garmin</button>
    <div id="stGarmin" class="status"></div>
  </div>

  <div class="card">
    <h2>📷 Ler de uma imagem</h2>
    <p class="hint">Tire um print da tela de zonas no app/relógio Garmin e envie — a IA preenche os campos.</p>
    <div class="upload-row">
      <input type="file" id="img" accept="image/*">
      <button class="sec" id="btnLer" style="width:auto;padding:11px 16px;margin-top:0" onclick="lerImagem()">🤖 Ler zonas</button>
    </div>
    <div id="stImg" class="status"></div>
  </div>

  <div class="card">
    <h2>✏️ Zonas (bpm)</h2>
    <p class="hint">Min e max de cada zona. Edite manualmente a qualquer momento.</p>
    <div id="zonas"></div>
    <button id="btnSalvarZonas" onclick="salvarZonas()">💾 Salvar zonas</button>
    <div id="st-zonas" class="status"></div>
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
    aplicarZonas(await r.json());
  } catch(e) { renderZonas([]); }
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

// ── Academia ──
const _ACA_DIAS_NOMES = ['Segunda-feira','Terça-feira','Quarta-feira','Quinta-feira','Sexta-feira','Sábado','Domingo'];
let _academiaTreina = '{{ACADEMIA_TREINA}}' === '1';
let _academiaDisp = {{ACADEMIA_DISP_JSON}};

function setAcademia(v) {
  _academiaTreina = v;
  document.getElementById('aca-sim').classList.toggle('aca-active', v);
  document.getElementById('aca-nao').classList.toggle('aca-active', !v);
  document.getElementById('aca-dias').style.display = v ? '' : 'none';
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
</script>
</body>
</html>"""
