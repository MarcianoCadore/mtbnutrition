"""Prova de que o atleta está melhorando.

O motivo nº 1 de cancelamento em assinatura de treino é não enxergar progresso.
A landing promete "sua evolução" no painel; até agora isso não existia.

**Isto não é o PMC.** A decisão de não exibir CTL/ATL/TSB continua de pé (ver
memória do polimento): nos dados reais o CTL parte do zero e marca "alto risco"
em metade dos dias do primeiro mês e meio — justo quando o assinante decide se
o app presta. O que entra aqui são métricas que **não mentem com pouco dado**:

- **curva de potência** — o gráfico que o ciclista entende, e que compara o
  atleta com ele mesmo de 90 dias atrás;
- **FTP no tempo** — o número que ele já persegue;
- **volume e carga por semana** — sobe, desce, sumiu;
- **aderência** — quantos dos treinos planejados ele de fato fez.
"""
import logging
from datetime import datetime, timedelta, timezone

from app.services.mongo_service import get_db

logger = logging.getLogger(__name__)

SEMANAS_PADRAO = 12


def _semana_de(data_iso: str) -> str:
    d = datetime.strptime(data_iso, "%Y-%m-%d").date()
    return (d - timedelta(days=d.weekday())).isoformat()


async def resumo_semanal(user_id: str, semanas: int = SEMANAS_PADRAO) -> list[dict]:
    """Volume, carga e aderência por semana, da mais antiga para a mais nova.

    Semanas sem nenhum treino executado entram zeradas de propósito: o buraco
    no gráfico é informação — é onde a rotina furou.
    """
    hoje = datetime.now(timezone.utc).date()
    inicio = _semana_de((hoje - timedelta(weeks=semanas - 1)).isoformat())

    db = get_db()
    cursor = db.semanas.find(
        {"user_id": user_id, "semana_inicio": {"$gte": inicio}},
        {"semana_inicio": 1, "treinos": 1},
    )
    por_semana = {doc["semana_inicio"]: doc async for doc in cursor}

    saida = []
    for i in range(semanas):
        chave = _semana_de((hoje - timedelta(weeks=semanas - 1 - i)).isoformat())
        doc = por_semana.get(chave)
        linha = {"semana": chave, "tss": 0, "minutos": 0, "km": 0.0,
                 "sessoes": 0, "planejados": 0}

        for t in (doc or {}).get("treinos", []):
            if t.get("tipo") == "DESCANSO":
                continue
            r = t.get("resultado") or {}
            if t.get("origem") != "backfill":
                linha["planejados"] += 1
            if not r:
                continue
            linha["sessoes"] += 1
            linha["tss"] += int(r.get("tss_obtido") or 0)
            linha["minutos"] += int(r.get("duracao_min") or 0)
            linha["km"] += float(r.get("distancia_km") or 0)

        linha["km"] = round(linha["km"], 1)
        linha["aderencia"] = (
            round(100 * linha["sessoes"] / linha["planejados"])
            if linha["planejados"] else None
        )
        saida.append(linha)

    return saida


async def historico_ftp(user_id: str) -> list[dict]:
    """FTP ao longo do tempo.

    O perfil guarda só o valor atual, então a série vive em `db.ftp_historico`,
    alimentada por `registrar_ftp` a cada vez que o FTP muda — por teste ou por
    estimativa da curva.
    """
    db = get_db()
    pontos = []

    cursor = db.ftp_historico.find({"user_id": user_id}).sort("data", 1)
    async for doc in cursor:
        pontos.append({"data": doc["data"], "ftp": doc["ftp"],
                       "origem": doc.get("origem", "teste")})
    return pontos


async def registrar_ftp(user_id: str, ftp: int, origem: str = "teste") -> None:
    """Guarda um ponto na série do FTP.

    Um documento por dia por atleta: várias sessões no mesmo dia não devem
    virar vários pontos no gráfico.
    """
    hoje = datetime.now(timezone.utc).date().isoformat()
    await get_db().ftp_historico.update_one(
        {"user_id": user_id, "data": hoje},
        {"$set": {"ftp": int(ftp), "origem": origem,
                  "em": datetime.now(timezone.utc)}},
        upsert=True,
    )


async def resumo(user_id: str, semanas: int = SEMANAS_PADRAO) -> dict:
    """Tudo que a tela de evolução precisa, numa chamada."""
    from app.services.config_service import get_ftp
    from app.services.potencia_service import estimar_ftp, get_curva

    curva = await get_curva(user_id)
    ftp_atual, _ = await get_ftp(user_id)
    estimado, como = estimar_ftp(curva)
    semanal = await resumo_semanal(user_id, semanas)

    executadas = [s for s in semanal if s["sessoes"]]
    with_tss = [s["tss"] for s in semanal if s["tss"]]

    return {
        "semanal": semanal,
        "curva": [
            {"duracao_s": d, "watts": v["watts"], "data": v.get("data")}
            for d, v in sorted(curva.items())
        ],
        "ftp": {"atual": ftp_atual, "estimado": estimado, "estimado_de": como},
        "ftp_historico": await historico_ftp(user_id),
        "totais": {
            "semanas_com_treino": len(executadas),
            "sessoes":  sum(s["sessoes"] for s in semanal),
            "horas":    round(sum(s["minutos"] for s in semanal) / 60),
            "km":       round(sum(s["km"] for s in semanal)),
            "tss_medio": round(sum(with_tss) / len(with_tss)) if with_tss else None,
        },
    }
