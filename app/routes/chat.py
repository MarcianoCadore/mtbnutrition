from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.services import chat_service

router = APIRouter()


class MensagemInput(BaseModel):
    texto: str


@router.get("/historico")
async def historico(request: Request):
    user_id = request.state.user_id
    msgs = await chat_service.get_historico(user_id, limite=30)
    return JSONResponse({"mensagens": msgs})


@router.post("/mensagem")
async def mensagem(request: Request, body: MensagemInput):
    user_id = request.state.user_id
    texto = body.texto.strip()
    if not texto:
        return JSONResponse({"erro": "Mensagem vazia"}, status_code=400)
    resposta, recarregar = await chat_service.responder(user_id, texto)
    return JSONResponse({"resposta": resposta, "recarregar": recarregar})
