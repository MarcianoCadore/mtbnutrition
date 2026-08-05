"""Curva de potência e FTP estimado (eFTP).

O FTP é a régua de quase tudo aqui: os alvos em watts das prescrições, o
arquivo `.zwo` (que é relativo ao FTP), o pTSS e, por tabela, a carga crônica
que ancora o polimento. Até agora ele só existia se o atleta fizesse um teste
de 20 minutos ou importasse do Garmin — quem não fazia rodava com watts
errados ou sem watts nenhum.

Este módulo tira o FTP do que o atleta já pedalou. Cada `.fit` sincronizado
contribui com seus melhores esforços; a curva guarda o melhor de cada duração
nos últimos 90 dias, e o eFTP sai do melhor 20 min × 0,95 (protocolo clássico
de Coggan) ou do melhor 60 min direto, o que for maior.

**O eFTP só sobe sozinho.** Um treino fraco, uma pedalada de recuperação ou um
dia de vento contra não podem derrubar o FTP do atleta e estragar todos os
alvos da semana seguinte — cair é decisão dele, no teste ou no perfil.
"""
import logging
from datetime import datetime, timedelta, timezone

from app.services.mongo_service import get_db

logger = logging.getLogger(__name__)

JANELA_DIAS = 90
"""Curva de 90 dias: o suficiente para pegar um bloco de treino inteiro sem
carregar a forma do ano passado."""

_FATOR_20MIN = 0.95
"""Protocolo de Coggan: FTP ≈ 95% da melhor potência média de 20 minutos."""

MARGEM_SUBIDA = 0.02
"""Só reescreve o FTP se o eFTP superar o atual em 2% — evita trocar 250W por
251W e recalcular a semana inteira por ruído de medição."""

FTP_MIN, FTP_MAX = 80, 600


# ─── Curva ───────────────────────────────────────────────────────────────────

async def registrar_esforcos(user_id: str, data_iso: str, esforcos: dict[int, int]) -> dict:
    """Guarda os melhores esforços de uma sessão, mantendo o recorde por duração.

    Um documento por atleta: {duracao: {watts, data}}. Guardar todas as sessões
    daria histórico mais rico, mas a curva é lida a cada geração de semana e o
    recorde é a única coisa que o eFTP usa.
    """
    if not esforcos:
        return {}

    db = get_db()
    doc = await db.curva_potencia.find_one({"_id": user_id}) or {}
    curva = doc.get("curva") or {}
    mudou = False

    for dur, watts in esforcos.items():
        chave = str(dur)
        atual = curva.get(chave) or {}
        if not _dentro_da_janela(atual.get("data")) or watts > (atual.get("watts") or 0):
            curva[chave] = {"watts": int(watts), "data": data_iso}
            mudou = True

    if mudou:
        await db.curva_potencia.update_one(
            {"_id": user_id},
            {"$set": {"curva": curva, "atualizado_em": datetime.now(timezone.utc)}},
            upsert=True,
        )
    return curva


def _dentro_da_janela(data_iso: str | None, ref: datetime | None = None) -> bool:
    """Recorde velho não vale mais: a forma de 4 meses atrás não é a de hoje."""
    if not data_iso:
        return False
    try:
        d = datetime.strptime(data_iso, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    limite = (ref or datetime.now(timezone.utc)) - timedelta(days=JANELA_DIAS)
    return d >= limite


async def get_curva(user_id: str) -> dict[int, dict]:
    """{duracao_s: {watts, data}} apenas com recordes dentro da janela."""
    doc = await get_db().curva_potencia.find_one({"_id": user_id})
    if not doc:
        return {}
    return {
        int(dur): dados
        for dur, dados in (doc.get("curva") or {}).items()
        if _dentro_da_janela(dados.get("data"))
    }


# ─── eFTP ────────────────────────────────────────────────────────────────────

def estimar_ftp(curva: dict[int, dict]) -> tuple[int | None, str]:
    """(watts, como_foi_estimado). (None, "") se a curva não permite estimar.

    Prefere o esforço de 60 min quando existe — é o próprio FTP por definição,
    sem fator de correção. Cai para 20 min × 0,95 no caso comum.
    """
    def watts(dur):
        return (curva.get(dur) or {}).get("watts")

    hora = watts(3600)
    if hora:
        return _limitar(hora), "melhor 60 min"

    vinte = watts(1200)
    if vinte:
        return _limitar(round(vinte * _FATOR_20MIN)), "melhor 20 min × 0,95"

    return None, ""


def _limitar(valor: int) -> int:
    return max(FTP_MIN, min(FTP_MAX, int(valor)))


async def talvez_atualizar_ftp(user_id: str) -> dict | None:
    """Sobe o FTP se a curva mostra que o atleta melhorou. Nunca desce.

    Devolve {ftp, anterior, origem} quando atualiza; None quando não há motivo.
    """
    from app.services.config_service import get_ftp, salvar_ftp

    curva = await get_curva(user_id)
    estimado, como = estimar_ftp(curva)
    if not estimado:
        return None

    atual, modo = await get_ftp(user_id)

    if atual and estimado <= atual * (1 + MARGEM_SUBIDA):
        return None

    # Preserva o modo de potência escolhido pelo atleta — a estimativa muda o
    # número, não a preferência de onde os watts aparecem.
    await salvar_ftp(user_id, estimado, modo=modo, origem="estimado")
    logger.info("eFTP de %s: %sW → %sW (%s)", user_id, atual, estimado, como)
    return {"ftp": estimado, "anterior": atual, "origem": como}


async def processar_fit(user_id: str, data_iso: str, fit_path: str) -> dict | None:
    """Extrai a curva de um .fit e atualiza o eFTP se for o caso.

    Chamado no sync e no backfill. Nunca levanta: uma falha aqui não pode
    impedir o treino de ser registrado.
    """
    try:
        from app.services.fit_service import curva_de_potencia
        esforcos = curva_de_potencia(fit_path)
        if not esforcos:
            return None
        await registrar_esforcos(user_id, data_iso, esforcos)
        return await talvez_atualizar_ftp(user_id)
    except Exception as exc:
        logger.warning("curva de potência falhou para %s (%s): %s", user_id, fit_path, exc)
        return None
