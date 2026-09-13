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


# ─── Retrospectiva por período ───────────────────────────────────────────────
#
# "Como vêm vindo meus treinos?" é uma pergunta de bloco, não de semana: só
# aparece quando se olha 1, 3 ou 6 meses de uma vez. A matéria-prima já existe —
# cada treino executado guarda `resultado.analise_ia` com pontos fortes e fracos
# escritos na hora. O que faltava era juntar.
#
# Nada aqui chama IA. As frases já foram escritas; agrupá-las por tema é conta,
# e conta não precisa de modelo — roda instantâneo e não custa nada.

# Cada tema é reconhecido por palavras que aparecem de fato nas avaliações. A
# ordem importa: a primeira que casar leva o ponto, então o mais específico vem
# antes do mais genérico.
_TEMAS = (
    ("cadencia",    "Cadência",              ("cadência", "cadencia", "rpm")),
    ("academia",    "Academia e cargas",     ("exercício", "exercicio", " kg", "série", "serie", "agachamento", "leg press")),
    ("potencia",    "Potência e medidor",    ("watts", "potência", "potencia", " np ", "medidor", " if ", "ftp")),
    ("zonas",       "Zonas e intensidade",   ("zona", " z1", " z2", " z3", " z4", " z5", "intensidade", "all-out", "limiar")),
    ("volume",      "Volume das sessões",    ("volume", "duração", "duracao", "min abaixo", "interromp", "encerr", "planejado")),
    ("terreno",     "Terreno e altimetria",  ("elevação", "elevacao", "altimetria", "subida", "terreno", "rota")),
    ("carga",       "Carga e fadiga",        ("tss", "carga", "fadiga", "recuperação", "recuperacao")),
    ("fc",          "Frequência cardíaca",   ("bpm", "fc ", "cardíac", "cardiac", "cinta")),
)


def _tema_de(frase: str) -> tuple[str, str] | None:
    texto = f" {(frase or '').lower()} "
    for chave, rotulo, termos in _TEMAS:
        if any(t in texto for t in termos):
            return chave, rotulo
    return None


def _meses_atras(d, n: int):
    """Mesma data n meses antes, encolhendo o dia quando o mês é mais curto."""
    ano, mes = d.year, d.month - n
    while mes <= 0:
        mes += 12
        ano -= 1
    dia = min(d.day, [31, 29 if ano % 4 == 0 and (ano % 100 or ano % 400 == 0) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mes - 1])
    return d.replace(year=ano, month=mes, day=dia)


def _agrupar(frases_por_sessao: list[list[str]], limite: int = 5) -> list[dict]:
    """Conta em quantas SESSÕES cada tema apareceu, não quantas frases existem.

    Uma sessão que repete "cadência baixa" em três frases é um problema, não
    três — contar frase inflaria o tema mais falante em vez do mais frequente.
    """
    contagem: dict[str, dict] = {}
    for frases in frases_por_sessao:
        vistos = set()
        for frase in frases:
            achado = _tema_de(frase)
            if not achado:
                continue
            chave, rotulo = achado
            if chave in vistos:
                continue
            vistos.add(chave)
            item = contagem.setdefault(chave, {"tema": chave, "rotulo": rotulo,
                                               "n": 0, "exemplo": frase})
            item["n"] += 1
    return sorted(contagem.values(), key=lambda x: -x["n"])[:limite]


def _janela(user_id: str, de: str, ate: str):
    return {"user_id": user_id, "semana_inicio": {"$gte": _semana_de(de),
                                                  "$lte": ate}}


async def _coletar(user_id: str, de: str, ate: str) -> dict:
    """Números crus de um intervalo de datas (inclusive nas duas pontas)."""
    db = get_db()
    dados = {
        "sessoes": 0, "planejados": 0, "minutos": 0, "minutos_plan": 0,
        "km": 0.0, "elevacao": 0, "tss": 0, "notas": [], "cadencias": [],
        "fortes": [], "fracos": [], "desvios": [], "melhor": None, "pior": None,
    }
    cursor = db.semanas.find(_janela(user_id, de, ate), {"treinos": 1})
    async for doc in cursor:
        for t in doc.get("treinos", []):
            data = t.get("data") or ""
            if not (de <= data <= ate) or t.get("tipo") == "DESCANSO":
                continue
            if t.get("origem") not in ("extra", "backfill"):
                dados["planejados"] += 1
                dados["minutos_plan"] += int(t.get("duracao_min") or 0)
            r = t.get("resultado") or {}
            if not r:
                continue
            dados["sessoes"] += 1
            dados["minutos"] += int(r.get("duracao_min") or 0)
            dados["km"] += float(r.get("distancia_km") or 0)
            dados["elevacao"] += int(r.get("elevacao_m") or 0)
            dados["tss"] += int(r.get("tss_obtido") or 0)
            if r.get("cadencia_media_rpm"):
                dados["cadencias"].append(int(r["cadencia_media_rpm"]))

            # Treino que saiu diferente do que foi prescrito. O tipo lido vem do
            # classificador em cima do FIT — é a leitura do que o corpo fez, não
            # do que estava escrito no plano.
            lido = r.get("tipo_realizado")
            if lido and t.get("tipo") and lido != t["tipo"]:
                dados["desvios"].append({"data": data, "planejado": t["tipo"], "realizado": lido})

            a = r.get("analise_ia") or {}
            if a.get("pontos_fortes"):
                dados["fortes"].append(list(a["pontos_fortes"]))
            if a.get("pontos_fracos"):
                dados["fracos"].append(list(a["pontos_fracos"]))
            nota = a.get("nota")
            if nota is not None:
                dados["notas"].append(float(nota))
                sessao = {"data": data, "tipo": t.get("tipo"), "nota": float(nota),
                          "resumo": a.get("resumo") or ""}
                if not dados["melhor"] or float(nota) > dados["melhor"]["nota"]:
                    dados["melhor"] = sessao
                if not dados["pior"] or float(nota) < dados["pior"]["nota"]:
                    dados["pior"] = sessao
    return dados


def _resumir(d: dict) -> dict:
    notas = d["notas"]
    cad = d["cadencias"]
    return {
        "sessoes": d["sessoes"],
        "planejados": d["planejados"],
        "aderencia": round(100 * d["sessoes"] / d["planejados"]) if d["planejados"] else None,
        "horas": round(d["minutos"] / 60, 1),
        "horas_plan": round(d["minutos_plan"] / 60, 1),
        "km": round(d["km"]),
        "elevacao": d["elevacao"],
        "tss": d["tss"],
        "nota_media": round(sum(notas) / len(notas), 1) if notas else None,
        "cadencia_media": round(sum(cad) / len(cad)) if cad else None,
    }


async def retrospectiva(user_id: str, meses: int = 1) -> dict:
    """Como os treinos vêm vindo nos últimos N meses, contra os N anteriores.

    O período anterior de mesmo tamanho entra junto porque "40 horas" não diz
    nada sozinho: o que informa é 40 contra 28, ou 40 contra 52.
    """
    hoje = datetime.now(timezone.utc).date()
    inicio = _meses_atras(hoje, meses)
    inicio_anterior = _meses_atras(inicio, meses)

    atual = await _coletar(user_id, inicio.isoformat(), hoje.isoformat())
    anterior = await _coletar(user_id, inicio_anterior.isoformat(),
                              (inicio - timedelta(days=1)).isoformat())

    resumo_atual = _resumir(atual)
    resumo_anterior = _resumir(anterior)

    # Desvio de tipo agrupado: o mesmo erro repetido é padrão, não acidente.
    por_par: dict[str, dict] = {}
    for dv in atual["desvios"]:
        chave = f"{dv['planejado']}→{dv['realizado']}"
        item = por_par.setdefault(chave, {"planejado": dv["planejado"],
                                          "realizado": dv["realizado"],
                                          "n": 0, "datas": []})
        item["n"] += 1
        item["datas"].append(dv["data"])

    return {
        "meses": meses,
        "de": inicio.isoformat(),
        "ate": hoje.isoformat(),
        "atual": resumo_atual,
        "anterior": resumo_anterior,
        "fortes": _agrupar(atual["fortes"]),
        "fracos": _agrupar(atual["fracos"]),
        "desvios": sorted(por_par.values(), key=lambda x: -x["n"])[:5],
        "desvios_total": len(atual["desvios"]),
        "melhor": atual["melhor"],
        "pior": atual["pior"],
    }
