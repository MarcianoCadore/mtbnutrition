"""Estado da assinatura: trial, ativa, expirada.

Antes deste módulo o portal não tinha paywall nenhum. O gate de acesso era o
campo `telefone_verificado`, que o admin ligava à mão depois de receber o
comprovante no WhatsApp — misturando "este número existe" com "esta pessoa
pagou". Aqui os dois conceitos ficam separados:

    telefone_verificado  → pode receber WhatsApp
    assinatura.status    → pode usar a plataforma

Estados possíveis (campo `assinatura` no doc do usuário):

    trial     — cadastrou e está nos 14 dias grátis. Acesso total.
    ativa     — pagamento confirmado; vale até `pago_ate`. Acesso total.
    expirada  — trial acabou ou a mensalidade venceu. Só leitura (ver
                `MODO_LEITURA`), o resto redireciona para /assinar.
    cancelada — desligada à mão pelo admin. Mesmo efeito de expirada, mas
                não volta sozinha e não recebe aviso de vencimento.

A cobrança continua manual (Pix + comprovante no WhatsApp do Marciano) — este
módulo só decide quem entra. Quando entrar gateway de verdade, o webhook do
gateway chama `confirmar_pagamento()` e nada mais muda.
"""
import logging
import math
from datetime import datetime, timedelta, timezone

from bson import ObjectId

from app.services.mongo_service import get_db

logger = logging.getLogger(__name__)

# ─── Parâmetros do plano ─────────────────────────────────────────────────────

TRIAL_DIAS = 14
"""14 e não 7 de propósito: o diferencial da plataforma é a IA recalibrar a
semana a partir do que o atleta executou, e isso só acontece na virada da
semana. Com 7 dias ele decide se paga antes de ver o produto fazer a única
coisa que o TrainingPeaks e o intervals.icu não fazem."""

CICLO_DIAS = 30

AVISOS_DIAS = (3, 1)
"""Dias restantes que disparam aviso no WhatsApp. O dia 0 (venceu) tem
mensagem própria."""

STATUS_COM_ACESSO = ("trial", "ativa")


# ─── Leitura do estado ───────────────────────────────────────────────────────

def _aware(dt):
    """Datas voltam do Mongo sem tzinfo; compara tudo em UTC."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def novo_trial(inicio: datetime | None = None) -> dict:
    """Bloco `assinatura` de quem acabou de se cadastrar."""
    inicio = inicio or datetime.now(timezone.utc)
    return {
        "status": "trial",
        "trial_inicio": inicio,
        "trial_fim": inicio + timedelta(days=TRIAL_DIAS),
        "pago_ate": None,
        "confirmado_em": None,
        "avisos_enviados": [],
    }


def _bloco(u: dict | None) -> dict:
    """Assinatura do usuário, com fallback para contas anteriores ao paywall.

    Quem já existia quando isto entrou no ar não tinha o campo. Tratar como
    trial recém-começado daria 14 dias grátis a quem já paga, e tratar como
    expirada trancaria o Marciano para fora do próprio app. O fallback é
    `ativa` sem vencimento — a migração (scripts/migrar_assinaturas.py) grava
    o estado real de cada um."""
    if not u:
        return {"status": "expirada"}
    a = u.get("assinatura")
    if isinstance(a, dict) and a.get("status"):
        return a
    return {"status": "ativa", "pago_ate": None, "legado": True}


def dias_restantes(u: dict | None, ref: datetime | None = None) -> int | None:
    """Dias até o fim do trial ou do ciclo pago. None se não expira.

    Arredonda para cima: faltando 30 minutos, ainda é "1 dia" — dizer "0 dias"
    para quem tem acesso confunde.
    """
    a = _bloco(u)
    ref = ref or datetime.now(timezone.utc)
    fim = _aware(a.get("trial_fim") if a.get("status") == "trial" else a.get("pago_ate"))
    if fim is None:
        return None
    segundos = (fim - ref).total_seconds()
    if segundos <= 0:
        return 0
    return max(1, math.ceil(segundos / 86400))


def estado(u: dict | None, ref: datetime | None = None) -> dict:
    """Situação da assinatura para o middleware, o banner e o admin.

    Calcula o vencimento na leitura em vez de confiar no `status` gravado: o
    job diário pode não ter rodado (servidor reiniciado, hora errada) e ninguém
    deve continuar entrando por causa disso.
    """
    a = _bloco(u)
    status = a.get("status", "expirada")
    ref = ref or datetime.now(timezone.utc)

    vencida = False
    if status == "trial":
        fim = _aware(a.get("trial_fim"))
        vencida = fim is not None and ref >= fim
    elif status == "ativa":
        fim = _aware(a.get("pago_ate"))
        vencida = fim is not None and ref >= fim

    if vencida:
        status = "expirada"

    return {
        "status":     status,
        "acesso":     status in STATUS_COM_ACESSO,
        "em_trial":   status == "trial",
        "dias":       0 if vencida else dias_restantes(u, ref),
        "pago_ate":   _aware(a.get("pago_ate")),
        "trial_fim":  _aware(a.get("trial_fim")),
    }


async def estado_por_id(user_id) -> dict | None:
    """Estado da assinatura pelo id. Usada pelo middleware a cada requisição.

    Devolve **None** quando não há usuário com esse id — conta apagada, id
    inválido. Esse caso não é do gate de assinatura: mandar um ex-usuário para
    a tela de "pague R$ 24,99" é a resposta errada. Quem trata é a
    autenticação, que o levará ao login.
    """
    db = get_db()
    try:
        oid = user_id if isinstance(user_id, ObjectId) else ObjectId(str(user_id))
    except Exception:
        return None
    u = await db.users.find_one({"_id": oid}, {"assinatura": 1})
    if u is None:
        return None
    return estado(u)


# ─── Escrita ─────────────────────────────────────────────────────────────────

async def iniciar_trial(user_id) -> dict:
    """Marca o início do trial. Chamado no cadastro."""
    bloco = novo_trial()
    await _set(user_id, {"assinatura": bloco})
    logger.info("Trial iniciado para %s até %s", user_id, bloco["trial_fim"].date())
    return bloco


async def confirmar_pagamento(user_id, ciclos: int = 1) -> dict:
    """Libera CICLO_DIAS × ciclos de acesso a partir de hoje (ou do vencimento).

    Se ainda há saldo — pagou adiantado, ou o trial não acabou — soma em cima do
    que resta em vez de zerar. Quem paga no dia 10 de um trial de 14 não pode
    perder os 4 dias restantes por ter pago cedo.
    """
    db = get_db()
    oid = ObjectId(str(user_id))
    u = await db.users.find_one({"_id": oid}, {"assinatura": 1})
    agora = datetime.now(timezone.utc)

    est = estado(u, agora)
    base = agora
    if est["acesso"]:
        saldo = est.get("pago_ate") or est.get("trial_fim")
        if saldo and saldo > agora:
            base = saldo

    novo_fim = base + timedelta(days=CICLO_DIAS * max(1, ciclos))
    campos = {
        "assinatura.status":        "ativa",
        "assinatura.pago_ate":      novo_fim,
        "assinatura.confirmado_em": agora,
        "assinatura.avisos_enviados": [],
    }
    await db.users.update_one({"_id": oid}, {"$set": campos})
    logger.info("Pagamento confirmado para %s — acesso até %s", user_id, novo_fim.date())
    return {"status": "ativa", "pago_ate": novo_fim}


async def marcar_expirada(user_id) -> None:
    await _set(user_id, {"assinatura.status": "expirada"})


async def cancelar(user_id) -> None:
    """Desliga a assinatura à mão (inadimplência, pedido do usuário, abuso)."""
    await _set(user_id, {"assinatura.status": "cancelada"})


async def reabrir_trial(user_id, dias: int = TRIAL_DIAS) -> dict:
    """Concede (ou estende) trial. Só o admin chama — cortesia e suporte."""
    agora = datetime.now(timezone.utc)
    bloco = {
        "status": "trial",
        "trial_inicio": agora,
        "trial_fim": agora + timedelta(days=dias),
        "pago_ate": None,
        "confirmado_em": None,
        "avisos_enviados": [],
    }
    await _set(user_id, {"assinatura": bloco})
    return bloco


async def registrar_aviso(user_id, marcador: str) -> None:
    """Guarda que um aviso já foi mandado, para não repetir a cada rodada."""
    db = get_db()
    await db.users.update_one(
        {"_id": ObjectId(str(user_id))},
        {"$addToSet": {"assinatura.avisos_enviados": marcador}},
    )


async def _set(user_id, campos: dict) -> None:
    db = get_db()
    await db.users.update_one({"_id": ObjectId(str(user_id))}, {"$set": campos})
