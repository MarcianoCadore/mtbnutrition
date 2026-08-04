"""Reavaliação de treino quando os dados de frequência cardíaca não valem.

Sem cinta cardíaca — ou com a cinta sem bateria, bateria fraca ou mal
posicionada — a FC gravada vem ausente, travada ou absurdamente baixa. A
avaliação pós-treino sai injusta: o atleta leva nota baixa por "faltou
intensidade" num treino que executou certinho, e o TSS calculado por hrTSS
fica menor que o real.

Duas formas de marcar isso, disponíveis para QUALQUER usuário:
- pontual, por treino: `resultado.fc_invalida` — pelo chat ("ignora a FC de
  ontem, a cinta estava sem bateria") ou pelo botão no modal de avaliação;
- permanente, por atleta: `preferencias.sem_cinta_fc` — o toggle "não uso
  cinta cardíaca" no perfil, que passa a valer para todo treino novo.

Nos dois casos a análise é refeita ignorando FC, tempo em zonas de FC e o TSS
derivado de FC: a nota passa a sair de potência, volume e cadência.
"""

import logging
import os
from datetime import date, datetime, timedelta, timezone

from app.services.mongo_service import get_db

logger = logging.getLogger(__name__)

MOTIVO_PADRAO = "dados de FC não confiáveis (cinta cardíaca)"

# Marca em `resultado.origem` as sessões que o atleta contou em vez de o
# dispositivo ter gravado. Serve para não confundir com dado medido — e para o
# sync do Garmin/Strava poder sobrescrever sem dó quando a atividade chegar.
ORIGEM_RELATO = "relato_atleta"
MOTIVO_SEM_DISPOSITIVO = "sessão relatada pelo atleta, sem dados de dispositivo"


def _semana_de(data_iso: str) -> str:
    """Segunda-feira (ISO) da semana que contém data_iso."""
    d = date.fromisoformat(data_iso)
    return (d - timedelta(days=d.weekday())).isoformat()


# ── flags ────────────────────────────────────────────────────────────────────

async def usuario_sem_cinta(user_id) -> bool:
    """True se o atleta declarou no perfil que não usa cinta cardíaca."""
    if not user_id:
        return False
    try:
        from app.services.user_service import get_por_id
        u = await get_por_id(user_id) or {}
        return bool((u.get("preferencias") or {}).get("sem_cinta_fc"))
    except Exception:
        return False


async def deve_ignorar_fc(user_id, resultado: dict | None) -> bool:
    """True quando a FC deste treino não deve pesar na avaliação.

    Marcação pontual do treino tem prioridade; na ausência dela vale a
    preferência do atleta (sem cinta = nunca confiar na FC)."""
    if (resultado or {}).get("fc_invalida"):
        return True
    return await usuario_sem_cinta(user_id)


async def definir_uso_cinta(user_id, usa_cinta: bool) -> bool:
    """Salva se o atleta usa cinta cardíaca. Retorna `sem_cinta_fc` gravado."""
    from app.services.user_service import atualizar_usuario
    sem_cinta = not usa_cinta
    await atualizar_usuario(user_id, {"preferencias.sem_cinta_fc": sem_cinta})
    return sem_cinta


# ── reavaliação ──────────────────────────────────────────────────────────────

async def reavaliar_treino(user_id, data_iso: str, ignorar_fc: bool | None = None,
                           motivo: str | None = None) -> dict:
    """Refaz a avaliação (nota + análise + TSS) de um treino já realizado.

    `ignorar_fc=True` descarta a FC da análise e do TSS; `False` volta a
    considerá-la; `None` mantém o que já estava valendo (marcação do treino ou
    preferência do atleta) e só reprocessa.
    """
    from app.services.ai_service import analisar_atividade_pos_treino
    from app.services.garmin_service import UPLOADS_DIR, _metricas_extra

    db = get_db()
    semana = _semana_de(data_iso)
    doc = await db.semanas.find_one({"semana_inicio": semana, "user_id": str(user_id)})
    if not doc:
        raise ValueError(f"Não encontrei a semana de {data_iso} no calendário.")

    treino = next(
        (t for t in doc.get("treinos", [])
         if t.get("data") == data_iso and t.get("origem") != "extra"),
        None,
    )
    if not treino:
        raise ValueError(f"Não há treino em {data_iso}.")

    resultado = dict(treino.get("resultado") or {})
    if not resultado:
        raise ValueError(
            f"O treino de {data_iso} ainda não tem resultado sincronizado — "
            "não há o que reavaliar."
        )

    if ignorar_fc is None:
        ignorar_fc = await deve_ignorar_fc(user_id, resultado)

    if ignorar_fc:
        resultado["fc_invalida"] = True
        resultado["fc_invalida_motivo"] = motivo or MOTIVO_PADRAO
    else:
        resultado.pop("fc_invalida", None)
        resultado.pop("fc_invalida_motivo", None)

    fit_path = None
    if resultado.get("fit_file"):
        candidato = os.path.join(UPLOADS_DIR, semana, resultado["fit_file"])
        if os.path.exists(candidato):
            fit_path = candidato

    # TSS: o hrTSS mente junto com a FC — recalcula preferindo potência e
    # deixa o campo vazio se não sobrar métrica confiável (o card cai para o
    # "TSS previsto" do planejado).
    try:
        from app.services.config_service import get_zonas, get_ftp
        limiar = (await get_zonas(user_id) or {}).get("limiar")
        ftp_val, _ = await get_ftp(user_id)
    except Exception:
        limiar, ftp_val = None, None
    try:
        extras = _metricas_extra(
            treino, resultado, limiar,
            fit_path=fit_path, ftp=ftp_val, ignorar_fc=ignorar_fc,
        )
        resultado["tss_obtido"] = extras.get("tss_obtido")
        if extras.get("tss_esperado") is not None:
            resultado["tss_esperado"] = extras["tss_esperado"]
    except Exception as exc:
        logger.warning("reavaliar_treino: TSS não recalculado (%s): %s", data_iso, exc)
    if resultado.get("tss_obtido") is None:
        resultado.pop("tss_obtido", None)

    analise = await analisar_atividade_pos_treino(
        treino, resultado, user_id, fit_path, ignorar_fc=ignorar_fc
    )
    resultado["analise_ia"] = analise

    await db.semanas.update_one(
        {
            "semana_inicio": semana, "user_id": str(user_id),
            "treinos": {"$elemMatch": {"data": data_iso, "origem": {"$ne": "extra"}}},
        },
        {"$set": {"treinos.$.resultado": resultado}},
    )

    return {
        "data": data_iso,
        "semana_inicio": semana,
        "tipo": treino.get("tipo"),
        "fc_invalida": bool(ignorar_fc),
        "motivo": resultado.get("fc_invalida_motivo"),
        "nota": analise.get("nota"),
        "analise_ia": analise,
        "tss_obtido": resultado.get("tss_obtido"),
    }


# ── registro de sessão relatada pelo atleta ──────────────────────────────────

async def registrar_realizado(
    user_id,
    data_iso: str,
    duracao_min: int | None = None,
    relato: str | None = None,
    distancia_km: float | None = None,
    percepcao_esforco: int | None = None,
) -> dict:
    """Marca como REALIZADO um treino que o atleta relatou de viva voz.

    Existe para as sessões que nenhum dispositivo captura: academia, um pedal
    sem relógio, o rolo sem sensor. Antes disto o chat só tinha ferramentas de
    planejamento e "registrava" a sessão chamando `criar_treino_dia` — o que
    reescrevia a `descricao` do dia (destruindo a prescrição planejada) e não
    gravava nada em `resultado`: sem nota, sem TSS, fora da análise da semana.

    Escreve APENAS em `resultado`; o planejado (tipo, duração, descrição,
    sub-bloco de academia) fica intacto. Nunca sobrescreve resultado vindo de
    Garmin/Strava: dado medido vale mais que memória, e o re-sync o traria de
    volta de qualquer jeito.
    """
    from app.services.ai_service import analisar_atividade_pos_treino

    from app.utils import hoje_local

    if data_iso > hoje_local().isoformat():
        raise ValueError(
            f"{data_iso} ainda não chegou — não dá para registrar um treino "
            "que não aconteceu."
        )

    db = get_db()
    semana = _semana_de(data_iso)
    doc = await db.semanas.find_one({"semana_inicio": semana, "user_id": str(user_id)})
    if not doc:
        raise ValueError(f"Não encontrei a semana de {data_iso} no calendário.")

    treino = next(
        (t for t in doc.get("treinos", [])
         if t.get("data") == data_iso and t.get("origem") != "extra"),
        None,
    )
    if not treino or (treino.get("tipo") or "DESCANSO") == "DESCANSO":
        raise ValueError(
            f"{data_iso} não tem treino planejado — não há o que marcar como "
            "realizado. Se o atleta treinou fora do plano, agende o treino com "
            "adicionar_treino primeiro e só então registre."
        )

    anterior = treino.get("resultado") or {}
    if anterior.get("garmin_activity_id") or anterior.get("strava_activity_id"):
        raise ValueError(
            f"O treino de {data_iso} já foi sincronizado do dispositivo — o "
            "registro por relato não sobrescreve dado medido."
        )

    duracao = duracao_min or treino.get("duracao_min")
    if not duracao:
        raise ValueError(
            f"Informe a duração da sessão de {data_iso} — o planejado não tem "
            "duração para herdar."
        )

    # Sem dispositivo não existe FC. Marcar fc_invalida faz a análise entrar no
    # caminho "julgue pelo volume e pela execução" em vez de cobrar zonas que
    # ninguém mediu — ver deve_ignorar_fc() e o bloco SEM DADOS DE FC do prompt.
    resultado = {
        "origem": ORIGEM_RELATO,
        "duracao_min": int(duracao),
        "registrado_em": datetime.now(timezone.utc).isoformat(),
        "fc_invalida": True,
        "fc_invalida_motivo": MOTIVO_SEM_DISPOSITIVO,
    }
    if distancia_km:
        resultado["distancia_km"] = float(distancia_km)
    if percepcao_esforco:
        resultado["percepcao_esforco"] = int(percepcao_esforco)
    if relato and relato.strip():
        resultado["relato"] = relato.strip()

    # Sem potência e sem FC não há como calcular TSS: deixa `tss_obtido` fora
    # para o card cair no "TSS previsto" do planejado em vez de exibir um
    # número inventado.
    analise: dict = {}
    try:
        analise = await analisar_atividade_pos_treino(
            treino, resultado, user_id, None, ignorar_fc=True
        )
        resultado["analise_ia"] = analise
    except Exception as exc:
        logger.warning("registrar_realizado: análise falhou em %s: %s", data_iso, exc)

    await db.semanas.update_one(
        {
            "semana_inicio": semana, "user_id": str(user_id),
            "treinos": {"$elemMatch": {"data": data_iso, "origem": {"$ne": "extra"}}},
        },
        {"$set": {"treinos.$.resultado": resultado}},
    )
    logger.info(
        "registrar_realizado user=%s: %s tipo=%s dur=%smin (relato do atleta)",
        user_id, data_iso, treino.get("tipo"), duracao,
    )

    return {
        "data": data_iso,
        "semana_inicio": semana,
        "tipo": treino.get("tipo"),
        "duracao_min": int(duracao),
        "nota": analise.get("nota"),
        "analise_ia": analise,
    }


async def reavaliar_treinos_recentes(user_id, dias: int = 14,
                                     ignorar_fc: bool = True,
                                     motivo: str | None = None) -> list[dict]:
    """Reavalia todos os treinos com resultado dos últimos `dias` dias.

    Usado quando o atleta declara que não usa cinta: as avaliações antigas
    continuariam penalizando FC que nunca existiu."""
    from app.utils import hoje_local

    db = get_db()
    hoje = hoje_local()
    inicio = hoje - timedelta(days=max(1, dias))
    semanas = sorted({
        _semana_de((inicio + timedelta(days=i)).isoformat())
        for i in range((hoje - inicio).days + 1)
    })

    datas: list[str] = []
    async for doc in db.semanas.find(
        {"user_id": str(user_id), "semana_inicio": {"$in": semanas}}
    ):
        for t in doc.get("treinos", []):
            if t.get("origem") == "extra" or not t.get("resultado"):
                continue
            data = t.get("data") or ""
            if inicio.isoformat() <= data <= hoje.isoformat():
                datas.append(data)

    reavaliados = []
    for data in sorted(datas):
        try:
            reavaliados.append(
                await reavaliar_treino(user_id, data, ignorar_fc, motivo)
            )
        except Exception as exc:
            logger.warning("reavaliar_treinos_recentes: falhou em %s: %s", data, exc)
    return reavaliados
