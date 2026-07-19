"""Parecer fisiológico do atleta — passo 1 do pipeline da próxima semana.

Coleta as últimas semanas de treino (planejado × executado via Garmin),
calcula métricas de carga deterministicamente — o código é dono dos números —
e pede a um modelo especialista (Opus) um parecer estruturado de fisiologia
do exercício. O parecer alimenta o prompt da geração da próxima semana
(plano_semana_service) e fica salvo em `pareceres_fisiologicos` p/ o portal.

Nunca bloqueia a geração: sem histórico, sem API ou com erro de cota, devolve
um parecer determinístico calculado só das métricas.
"""

import json
import logging
from datetime import datetime, timezone

import anthropic
import pytz

from config.settings import settings
from app.services.mongo_service import get_db
from app.services.user_service import get_por_id

logger = logging.getLogger(__name__)

_client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
_MODEL_PARECER = "claude-opus-4-8"       # análise fisiológica (inteligência importa)
_MODEL_PARECER_FALLBACK = "claude-sonnet-5"
_TZ = pytz.timezone("America/Sao_Paulo")

_N_SEMANAS_HISTORICO = 4

# Limiares clássicos da razão carga aguda:crônica (ACWR) para risco de
# overtraining/subtreino. Fora da "sweet spot" (0.8–1.3) o ajuste é forçado.
_ACWR_ALTO = 1.3
_ACWR_BAIXO = 0.8
_ADERENCIA_MINIMA_PCT = 70

_NOMES_DIA = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


def _is_quota_error(exc: Exception) -> bool:
    if isinstance(exc, (anthropic.RateLimitError, anthropic.PermissionDeniedError)):
        return True
    msg = str(exc).lower()
    return any(k in msg for k in ("rate limit", "quota", "credit", "overloaded", "529"))


def _extrair_texto(response) -> str:
    """Primeiro bloco de texto da resposta (tolerante a blocos de thinking)."""
    return next(b.text for b in response.content if b.type == "text")


# ── Coleta do histórico ───────────────────────────────────────────────────────

async def _coletar_historico(user_id: str, semana_atual: str,
                             n_semanas: int = _N_SEMANAS_HISTORICO) -> list[dict]:
    """Últimas N semanas (incluindo a atual), da mais antiga para a mais recente.

    Cada semana vira um resumo compacto: só os campos que interessam ao
    fisiologista, extraídos do planejado e do `resultado` sincronizado do Garmin.
    """
    db = get_db()
    cursor = db.semanas.find(
        {"user_id": user_id, "semana_inicio": {"$lte": semana_atual}},
    ).sort("semana_inicio", -1).limit(n_semanas)
    docs = [d async for d in cursor]
    docs.reverse()  # mais antiga primeiro

    historico = []
    for doc in docs:
        treinos = []
        for t in doc.get("treinos", []):
            tipo = t.get("tipo") or "DESCANSO"
            res = t.get("resultado") or {}
            if tipo == "DESCANSO" and not res:
                continue
            ia = res.get("analise_ia") or {}
            treinos.append({
                "data":          t.get("data"),
                "tipo":          tipo,
                "planejado_min": t.get("duracao_min"),
                "executado":     bool(res),
                "real_min":      res.get("duracao_min"),
                "avg_hr":        res.get("avg_hr"),
                "max_hr":        res.get("max_hr"),
                "avg_power":     res.get("avg_power"),
                "norm_power":    res.get("norm_power"),
                "tss_obtido":    res.get("tss_obtido"),
                "tss_esperado":  res.get("tss_esperado"),
                "resumo_ia":     ia.get("resumo"),
                "pontos_fracos": ia.get("pontos_fracos") or [],
            })
        historico.append({"semana_inicio": doc.get("semana_inicio"), "treinos": treinos})
    return historico


# ── Métricas determinísticas (código é dono dos números) ─────────────────────

def calcular_metricas(historico: list[dict]) -> dict:
    """Carga (TSS), ACWR, aderência e padrão de furos a partir do histórico."""
    tss_semanal = []
    total_planejados = 0
    total_executados = 0
    furos_por_dia: dict[str, int] = {}

    for semana in historico:
        tss = 0
        tem_tss = False
        planejados = 0
        executados = 0
        for t in semana["treinos"]:
            if t["tipo"] == "DESCANSO":
                continue
            planejados += 1
            if t["executado"]:
                executados += 1
                if t["tss_obtido"] is not None:
                    tss += t["tss_obtido"]
                    tem_tss = True
            else:
                try:
                    wd = datetime.strptime(t["data"], "%Y-%m-%d").weekday()
                    nome = _NOMES_DIA[wd]
                    furos_por_dia[nome] = furos_por_dia.get(nome, 0) + 1
                except (ValueError, TypeError):
                    pass
        total_planejados += planejados
        total_executados += executados
        tss_semanal.append({
            "semana": semana["semana_inicio"],
            "tss": tss if tem_tss else None,
            "planejados": planejados,
            "executados": executados,
        })

    semanas_com_tss = [s["tss"] for s in tss_semanal if s["tss"] is not None]
    carga_aguda = tss_semanal[-1]["tss"] if tss_semanal else None
    carga_cronica = (
        round(sum(semanas_com_tss) / len(semanas_com_tss))
        if semanas_com_tss else None
    )
    acwr = None
    if carga_aguda is not None and carga_cronica and len(semanas_com_tss) >= 2:
        acwr = round(carga_aguda / carga_cronica, 2)

    aderencia_pct = (
        round(100 * total_executados / total_planejados)
        if total_planejados else None
    )

    return {
        "tss_semanal":   tss_semanal,
        "carga_aguda":   carga_aguda,
        "carga_cronica": carga_cronica,
        "acwr":          acwr,
        "aderencia_pct": aderencia_pct,
        "furos_por_dia": furos_por_dia,
    }


def _parecer_deterministico(metricas: dict) -> dict:
    """Parecer mínimo sem IA — regras clássicas de carga e aderência."""
    acwr = metricas.get("acwr")
    aderencia = metricas.get("aderencia_pct")

    if acwr is not None and acwr > _ACWR_ALTO:
        ajuste, fadiga = "reduzir", "alta"
        estado = (f"Carga aguda bem acima da crônica (ACWR {acwr}) — risco de "
                  "sobrecarga. Semana mais leve para absorver o treino.")
    elif acwr is not None and acwr < _ACWR_BAIXO:
        ajuste, fadiga = "aumentar", "baixa"
        estado = (f"Carga aguda abaixo da crônica (ACWR {acwr}) — espaço para "
                  "progredir volume/intensidade com segurança.")
    else:
        ajuste, fadiga = "manter", "moderada"
        estado = ("Carga na faixa segura (ou histórico insuficiente para ACWR). "
                  "Manter a progressão gradual planejada.")

    pontos = []
    recomendacoes = []
    if aderencia is not None and aderencia < _ADERENCIA_MINIMA_PCT:
        pontos.append(f"Aderência baixa ({aderencia}%) — plano acima da rotina real.")
        recomendacoes.append("Reduzir o número de sessões de qualidade e priorizar consistência.")
    furos = metricas.get("furos_por_dia") or {}
    if furos:
        pior = max(furos, key=furos.get)
        if furos[pior] >= 2:
            pontos.append(f"Furos recorrentes na {pior} ({furos[pior]}x nas últimas semanas).")
            recomendacoes.append(f"Evitar sessões-chave na {pior}; usar o dia para treino leve ou descanso.")

    return {
        "estado_forma":   estado,
        "nivel_fadiga":   fadiga,
        "ajuste_carga":   ajuste,
        "pontos_atencao": pontos,
        "recomendacoes":  recomendacoes,
    }


# ── Prompt e chamada ao modelo ───────────────────────────────────────────────

def _resumo_semana_prompt(semana: dict) -> str:
    linhas = [f"Semana {semana['semana_inicio']}:"]
    if not semana["treinos"]:
        linhas.append("  (sem treinos registrados)")
    for t in semana["treinos"]:
        if not t["executado"]:
            linhas.append(f"  - {t['data']} {t['tipo']} ({t['planejado_min']}min planejado) — NÃO REALIZADO")
            continue
        partes = [f"  - {t['data']} {t['tipo']}"]
        if t["planejado_min"] and t["real_min"]:
            partes.append(f"{t['real_min']}min (planejado {t['planejado_min']}min)")
        elif t["real_min"]:
            partes.append(f"{t['real_min']}min")
        if t["avg_hr"]:
            partes.append(f"FC {t['avg_hr']}bpm (máx {t['max_hr']})" if t["max_hr"] else f"FC {t['avg_hr']}bpm")
        if t["norm_power"]:
            partes.append(f"NP {t['norm_power']}W")
        elif t["avg_power"]:
            partes.append(f"{t['avg_power']}W")
        if t["tss_obtido"] is not None:
            tss_txt = f"TSS {t['tss_obtido']}"
            if t["tss_esperado"] is not None:
                tss_txt += f" (esperado {t['tss_esperado']})"
            partes.append(tss_txt)
        linhas.append(" | ".join(partes))
        if t["resumo_ia"]:
            linhas.append(f"      Avaliação: {t['resumo_ia']}")
        if t["pontos_fracos"]:
            linhas.append(f"      A melhorar: {'; '.join(t['pontos_fracos'])}")
    return "\n".join(linhas)


def _montar_prompt(atleta: dict, historico: list[dict], metricas: dict) -> str:
    m = metricas
    tss_txt = " | ".join(
        f"{s['semana']}: {s['tss'] if s['tss'] is not None else 'sem dados'} "
        f"({s['executados']}/{s['planejados']} treinos)"
        for s in m["tss_semanal"]
    ) or "sem histórico"
    furos_txt = ", ".join(f"{d} ({n}x)" for d, n in (m["furos_por_dia"] or {}).items()) or "nenhum"
    historico_txt = "\n\n".join(_resumo_semana_prompt(s) for s in historico) or "(sem histórico)"

    return f"""Você é um fisiologista do exercício com formação em educação física, especializado em ciclismo de montanha (MTB), periodização e análise de carga de treino.

Analise o histórico do atleta e produza um PARECER FISIOLÓGICO que orientará a montagem da próxima semana de treinos.

ATLETA: {atleta['nome']}, {atleta['idade']} anos, {atleta['peso']:.0f} kg, objetivo: {atleta['objetivo']}.
FCMÁX: {atleta['fc_max']} bpm{f" | Limiar: {atleta['limiar']} bpm" if atleta.get('limiar') else ""}{f" | FTP: {atleta['ftp']}W" if atleta.get('ftp') else ""}

MÉTRICAS CALCULADAS PELO SISTEMA (fonte da verdade — NÃO recalcule):
- TSS por semana: {tss_txt}
- Carga aguda: {m['carga_aguda'] if m['carga_aguda'] is not None else 'sem dados'} | Carga crônica: {m['carga_cronica'] if m['carga_cronica'] is not None else 'sem dados'} | ACWR: {m['acwr'] if m['acwr'] is not None else 'insuficiente'}
- Aderência ao plano: {f"{m['aderencia_pct']}%" if m['aderencia_pct'] is not None else 'sem dados'}
- Treinos não realizados por dia da semana: {furos_txt}

HISTÓRICO PLANEJADO × EXECUTADO (mais antiga → mais recente):
{historico_txt}

O QUE ANALISAR (com profundidade de fisiologista):
1. Absorção de carga: o atleta está assimilando o treino (FC estável/caindo para a mesma potência ou ritmo) ou acumulando fadiga (FC alta para esforços fáceis, TSS obtido muito acima do esperado)?
2. Execução das sessões de qualidade: nos VO2MAX/TIROS a FC chegou perto da zona-alvo? Blocos completos?
3. Padrões de aderência: furos concentrados em algum dia? Plano compatível com a rotina?
4. Pontos fracos recorrentes apontados nas avaliações pós-treino.
5. Relação carga aguda × crônica (use o ACWR calculado acima).

Responda APENAS em JSON válido, sem markdown, sem texto extra:
{{
  "estado_forma": "Diagnóstico fisiológico em 2-4 frases: como o corpo do atleta está respondendo ao treino.",
  "nivel_fadiga": "baixa|moderada|alta",
  "ajuste_carga": "aumentar|manter|reduzir",
  "pontos_atencao": ["risco ou fraqueza concreta observada nos dados", "..."],
  "recomendacoes": ["diretriz ACIONÁVEL para a próxima semana (tipo de sessão, volume, posicionamento na semana)", "..."]
}}

REGRAS:
- Cite intensidades pelo NOME da zona (Z1-Z5), NUNCA em bpm ou faixas de FC.
- Recomendações devem ser específicas ao que os DADOS mostram — nada genérico.
- Máximo 4 pontos de atenção e 5 recomendações.
- Se o histórico for curto/vazio, diga isso no estado_forma e recomende progressão conservadora."""


async def _chamar_parecer_ia(prompt: str) -> tuple[dict, str]:
    """Opus (fisiologista) com fallback para Sonnet em erro de cota.

    Retorna (parecer, nome_do_modelo). Levanta exceção se ambos falharem.
    """
    try:
        response = await _client.messages.create(
            model=_MODEL_PARECER,
            max_tokens=6000,
            thinking={"type": "enabled", "budget_tokens": 4096},
            messages=[{"role": "user", "content": prompt}],
        )
        modelo = "claude-opus"
    except Exception as e:
        if not _is_quota_error(e):
            raise
        logger.warning("Opus sem cota para parecer (%s) — tentando Sonnet", e)
        response = await _client.messages.create(
            model=_MODEL_PARECER_FALLBACK,
            max_tokens=6000,
            messages=[{"role": "user", "content": prompt}],
        )
        modelo = "claude-sonnet"

    raw = _extrair_texto(response).strip().replace("```json", "").replace("```", "").strip()
    return json.loads(raw), modelo


# ── Entrada principal ────────────────────────────────────────────────────────

async def gerar_parecer_fisiologico(user_id: str, semana_atual: str) -> dict:
    """Gera (e persiste) o parecer fisiológico das últimas semanas do atleta.

    Reaproveita o parecer já salvo para a mesma semana se foi gerado hoje —
    evita repetir a chamada cara ao Opus quando o usuário pré-visualiza a
    mesma semana mais de uma vez no mesmo dia.
    """
    db = get_db()
    existente = await db.pareceres_fisiologicos.find_one(
        {"user_id": user_id, "semana_ref": semana_atual})
    if existente and existente.get("modelo") in ("claude-opus", "claude-sonnet"):
        gerado_em = datetime.fromisoformat(existente["gerado_em"])
        if gerado_em.astimezone(_TZ).date() == datetime.now(_TZ).date():
            existente.pop("_id", None)
            return existente

    historico = await _coletar_historico(user_id, semana_atual)
    metricas = calcular_metricas(historico)

    u = await get_por_id(user_id) or {}
    perfil = u.get("perfil") or {}
    zonas_doc = u.get("zonas") or {}
    try:
        from app.services.config_service import get_zonas_potencia
        zp = await get_zonas_potencia(user_id)
        ftp = zp["ftp"] if zp else None
    except Exception:
        ftp = None
    atleta = {
        "nome":     u.get("nome") or "Atleta",
        "idade":    int(perfil.get("idade") or 34),
        "peso":     float(perfil.get("peso_kg") or 85),
        "objetivo": (u.get("preferencias") or {}).get("objetivo") or "performance",
        "fc_max":   int(zonas_doc.get("fc_max") or perfil.get("fc_max") or 190),
        "limiar":   zonas_doc.get("limiar") or perfil.get("limiar_bpm"),
        "ftp":      ftp,
    }

    prompt = _montar_prompt(atleta, historico, metricas)
    try:
        parecer_ia, modelo = await _chamar_parecer_ia(prompt)
    except Exception as e:
        logger.warning("Parecer via IA falhou (%s) — usando determinístico", e)
        parecer_ia, modelo = _parecer_deterministico(metricas), "deterministico"

    parecer = {
        "user_id":    user_id,
        "semana_ref": semana_atual,
        "gerado_em":  datetime.now(timezone.utc).isoformat(),
        "modelo":     modelo,
        "metricas":   metricas,
        **{k: parecer_ia.get(k) for k in
           ("estado_forma", "nivel_fadiga", "ajuste_carga", "pontos_atencao", "recomendacoes")},
    }

    await db.pareceres_fisiologicos.replace_one(
        {"user_id": user_id, "semana_ref": semana_atual}, parecer, upsert=True)
    parecer.pop("_id", None)
    return parecer


def bloco_parecer_prompt(parecer: dict | None) -> str:
    """Formata o parecer como bloco de prompt para a geração da próxima semana."""
    if not parecer:
        return ""
    m = parecer.get("metricas") or {}
    linhas = [
        "═══════════════════════════════════════════",
        "PARECER FISIOLÓGICO (últimas semanas — siga estas diretrizes ao montar a semana):",
        f"Estado de forma: {parecer.get('estado_forma', '')}",
        f"Fadiga: {parecer.get('nivel_fadiga', '?')} | Ajuste de carga recomendado: {(parecer.get('ajuste_carga') or 'manter').upper()}",
    ]
    if m.get("carga_aguda") is not None and m.get("carga_cronica") is not None:
        acwr_txt = f" (ACWR {m['acwr']})" if m.get("acwr") is not None else ""
        linhas.append(f"Carga: TSS aguda {m['carga_aguda']} vs crônica {m['carga_cronica']}{acwr_txt}")
    if m.get("aderencia_pct") is not None:
        linhas.append(f"Aderência ao plano: {m['aderencia_pct']}%")
    if parecer.get("pontos_atencao"):
        linhas.append("Pontos de atenção:")
        linhas += [f"  - {p}" for p in parecer["pontos_atencao"]]
    if parecer.get("recomendacoes"):
        linhas.append("Recomendações do fisiologista para a próxima semana (PRIORIZE-AS):")
        linhas += [f"  - {r}" for r in parecer["recomendacoes"]]
    linhas.append("═══════════════════════════════════════════")
    return "\n".join(linhas)
