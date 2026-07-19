from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.services import chat_service
from app.services.user_service import get_por_id

router = APIRouter()


class MensagemInput(BaseModel):
    texto: str


async def _chat_habilitado(user_id: str) -> bool:
    """Respeita o toggle `features.chat` do admin panel (ligado por padrão).
    O controle fino de custo é a quota semanal (`features.chat_limite_semana`)."""
    u = await get_por_id(user_id)
    return bool(u) and (u.get("features") or {}).get("chat") is not False


@router.get("/historico")
async def historico(request: Request):
    user_id = request.state.user_id
    if not await _chat_habilitado(user_id):
        return JSONResponse({"erro": "Chat não habilitado para este usuário."}, status_code=403)
    msgs = await chat_service.get_historico(user_id, limite=30)
    quota = await chat_service.quota_chat(user_id)
    return JSONResponse({"mensagens": msgs, **quota})


@router.post("/mensagem")
async def mensagem(request: Request, body: MensagemInput):
    user_id = request.state.user_id
    if not await _chat_habilitado(user_id):
        return JSONResponse({"erro": "Chat não habilitado para este usuário."}, status_code=403)
    texto = body.texto.strip()
    if not texto:
        return JSONResponse({"erro": "Mensagem vazia"}, status_code=400)

    quota = await chat_service.quota_chat(user_id)
    if quota["limite"] is not None and quota["restantes"] <= 0:
        return JSONResponse({
            "erro": (f"Você atingiu o limite de {quota['limite']} pergunta(s) desta "
                     "semana do plano gratuito. O limite renova toda segunda-feira."),
            **quota,
        }, status_code=429)

    resposta, recarregar = await chat_service.responder(user_id, texto)
    await chat_service.registrar_pergunta_chat(user_id)
    quota = await chat_service.quota_chat(user_id)
    return JSONResponse({"resposta": resposta, "recarregar": recarregar, **quota})
