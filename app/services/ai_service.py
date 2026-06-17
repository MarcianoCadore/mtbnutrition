import anthropic
import base64
import json
import re
from config.settings import settings
from app.models.models import Treino, TipoTreino, PlanoAlimentar
from datetime import datetime

_client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
_MODEL = "claude-sonnet-4-6"
_MODEL_ANALISE = "claude-opus-4-8"  # análise pós-treino: mais rico, ~20x/mês

KCAL_POR_TIPO = {
    TipoTreino.Z2_LONGO:    2500,
    TipoTreino.TIROS:       3200,
    TipoTreino.VO2MAX:      3200,
    TipoTreino.TEMPO:       2800,
    TipoTreino.FORCA:       2700,
    TipoTreino.RECUPERACAO: 2200,
    TipoTreino.DESCANSO:    2100,
}

def build_prompt(treino: Treino | None) -> str:
    tipo = treino.tipo if treino else TipoTreino.DESCANSO
    kcal = KCAL_POR_TIPO[tipo]

    treino_desc = ""
    if treino:
        treino_desc = f"""
Treino do dia:
- Tipo: {treino.tipo}
- Duração: {treino.duracao_min} minutos
- Distância: {treino.distancia_km or 'N/A'} km
- Elevação: {treino.elevacao_m or 'N/A'} m
- Calorias estimadas: {treino.calorias or 'N/A'} kcal
- Descrição: {treino.descricao or ''}
"""
    else:
        treino_desc = "Dia de descanso — sem treino."

    return f"""Você é um nutricionista esportivo especializado em ciclismo MTB.

Atleta: Marciano, 34 anos, 85kg, 1,81m, meta 78kg.
FC máxima: 192 bpm
Zonas: Z1 até 134 | Z2 135-153 | Z3 154-164 | Z4 165-177 | Z5 178+
Objetivo: emagrecer preservando músculo + performance MTB
Meta proteína: 187g/dia | Usa whey protein
Alimentos base preferidos: arroz, pão, carne, leite, queijo, iogurte, whey protein

{treino_desc}

Meta calórica do dia: {kcal} kcal (déficit inteligente de 300-400 kcal embutido)

Gere um plano alimentar completo para hoje com 4-5 refeições.
Use alimentos brasileiros comuns, práticos e acessíveis.
Evite carolinas, doces industrializados, açúcar refinado.
Inclua horários realistas (acorda ~6h, treina pela manhã).

Responda APENAS em JSON válido, sem markdown, sem texto extra:
{{
  "tipo_dia": "string",
  "kcal_total": number,
  "proteina_total_g": number,
  "refeicoes": [
    {{
      "horario": "HH:MM",
      "nome": "string",
      "itens": ["item1", "item2"],
      "kcal_estimado": number,
      "proteina_g": number,
      "carbo_g": number,
      "gordura_g": number,
      "observacao": "string ou null"
    }}
  ]
}}"""

_TIPOS_VALIDOS = {"Z2_LONGO", "TIROS", "VO2MAX", "TEMPO", "FORCA", "RECUPERACAO", "DESCANSO"}

# Palavras-chave por tipo de treino (regex, case-insensitive).
# Classificador determinístico — não depende da API de IA.
_PADROES_TIPO = {
    "VO2MAX": [
        r"vo\s*[2₂]\s*max", r"\bvo\s*[2₂]\b", r"\bv0?2\s*max\b",
        r"m[áa]x\s*consumo", r"consumo\s*m[áa]ximo",
    ],
    "TIROS": [
        r"\btiros?\b", r"\bsprints?\b", r"\bintervalos?\b", r"\bhiit\b",
        r"all[\s-]?out", r"\bm[áa]xim", r"\bexplos", r"neuromuscular",
        r"anaer[óo]bic", r"\bataques?\b", r"\bpiques?\b", r"\barranques?\b",
        r"\bz5\b",
    ],
    "TEMPO": [
        r"\btempo\b(?!\s+(?:total|de|em|na|no|m[ée]di[oa]|restante|gasto|parado))",
        r"\blimiar\b", r"\bthreshold\b", r"\bftp\b", r"sweet\s*spot",
        r"\bsweetspot\b", r"\blactat", r"\bz[34]\b", r"\bsubidas?\b",
        r"\bsst\b",
    ],
    "FORCA": [
        r"\bfor[çc]a\b", r"for[çc]a\s*espec[íi]fica", r"\btorque\b",
        r"baixa\s*cad[êe]ncia", r"cad[êe]ncia\s*baixa",
        r"\bsobremarcha\b", r"big\s*gear", r"marcha\s*pesada",
        r"\b(?:4[5-9]|5\d|6\d)\s*[-–a]?\s*\d*\s*rpm\b",  # cadência baixa em rpm (45-69)
        r"\bmuscula", r"\bresist[êe]ncia\s*muscular",
    ],
    "RECUPERACAO": [
        r"recupera", r"recovery", r"regenerativ", r"\bregen\b",
        r"\bsoltura\b", r"\bleve\b", r"\bz1\b", r"\beasy\b", r"\bsolta\b",
    ],
    "Z2_LONGO": [
        r"\bz2\b", r"\blongo\b", r"\blong\b", r"\bbase\b", r"endurance",
        r"aer[óo]bic", r"\bfundo\b", r"\brodagem\b", r"\bvolume\b",
        r"cad[êe]ncia", r"cadence", r"fundo\s*aer[óo]bico",
    ],
    "DESCANSO": [
        r"\bdescanso\b", r"\brest\b", r"\bfolga\b", r"\boff\b",
        r"day\s*off", r"dia\s*livre",
    ],
}

# Em caso de empate, vence o tipo mais específico/intenso (índice maior).
# FORCA fica acima de TEMPO e Z2_LONGO: "força específica em subida com cadência
# baixa" deve vencer os sinais genéricos de "subida" (TEMPO) e "cadência" (Z2).
_PRIORIDADE_TIPO = ["Z2_LONGO", "RECUPERACAO", "DESCANSO", "TEMPO", "FORCA", "TIROS", "VO2MAX"]


def _limpar_datas(texto: str) -> str:
    """Remove datas e dias da semana que poluem a classificação por texto."""
    t = re.sub(r"\b\d{4}-\d{1,2}-\d{1,2}\b", " ", texto)        # 2026-06-08
    t = re.sub(r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b", " ", t)  # 11/06, 08-06-2026
    t = re.sub(r"\b(?:segunda|ter[çc]a|quarta|quinta|sexta|s[áa]bado|domingo)"
               r"[\s-]*(?:feira)?\b", " ", t, flags=re.IGNORECASE)
    return t


def extrair_cadencia_texto(*textos: str | None) -> str | None:
    """Extrai um alvo de cadência (rpm) do texto livre das notas/descrição.

    Reconhece faixas ("50-60rpm" → "50-60") e valores únicos ("90rpm" → "90").
    Retorna None quando não há menção de cadência. Usado como fallback quando
    o workout do Garmin não traz um target de cadência estruturado.
    """
    for texto in textos:
        if not texto:
            continue
        m = re.search(r"(\d{2,3})\s*[-–a]\s*(\d{2,3})\s*rpm", texto, re.IGNORECASE)
        if m:
            return f"{m.group(1)}-{m.group(2)}"
        m2 = re.search(r"(\d{2,3})\s*rpm", texto, re.IGNORECASE)
        if m2:
            return m2.group(1)
    return None


def classificar_por_texto(*textos: str | None) -> str | None:
    """Classifica o tipo de treino por palavras-chave no título/descrição.

    O primeiro texto (título do treino) recebe peso maior. Retorna None
    quando nenhuma palavra-chave casa — aí o chamador usa outro sinal.
    """
    scores = {t: 0.0 for t in _PADROES_TIPO}
    for idx, texto in enumerate(textos):
        if not texto:
            continue
        t = _limpar_datas(texto.lower())
        peso = 3.0 if idx == 0 else 1.0  # idx 0 = título do treino
        for tipo, padroes in _PADROES_TIPO.items():
            for pat in padroes:
                if re.search(pat, t, re.IGNORECASE):
                    scores[tipo] += peso

    melhor = max(_PADROES_TIPO, key=lambda t: (scores[t], _PRIORIDADE_TIPO.index(t)))
    return melhor if scores[melhor] > 0 else None


async def classificar_tipo_treino(analise: dict) -> str:
    """Classifica o tipo de treino combinando texto, dados de FC e IA.

    Ordem de confiança:
      1. Palavras-chave no nome/notas/descrição (determinístico, confiável)
      2. Classificação por FC/potência do .fit (já feita em fit_service)
      3. Claude (último recurso)
    """
    # 1) Palavras-chave — título tem prioridade
    tipo_kw = classificar_por_texto(
        analise.get("workout_name"),
        analise.get("workout_notes"),
        analise.get("descricao_existente"),
        analise.get("descricao_estruturada"),
    )
    if tipo_kw:
        return tipo_kw

    # 2) Sinal de FC/potência do arquivo .fit (treino realizado)
    if analise.get("avg_hr") or analise.get("max_hr"):
        return analise.get("tipo", "Z2_LONGO")

    linhas = []
    if analise.get("workout_name"):
        linhas.append(f"Nome do treino: {analise['workout_name']}")
    if analise.get("duracao_min"):
        linhas.append(f"Duração: {analise['duracao_min']} min")
    if analise.get("avg_hr"):
        linhas.append(f"FC média: {analise['avg_hr']} bpm")
    if analise.get("max_hr"):
        linhas.append(f"FC máxima: {analise['max_hr']} bpm")
    if analise.get("distancia_km"):
        linhas.append(f"Distância: {analise['distancia_km']} km")
    if analise.get("descricao_existente"):
        linhas.append(f"\nDescrição do treino: {analise['descricao_existente']}")
    if analise.get("workout_notes"):
        linhas.append(f"\nNotas do treino: {analise['workout_notes']}")
    if analise.get("descricao_estruturada"):
        linhas.append(f"\nEstrutura planejada:\n{analise['descricao_estruturada']}")

    if not linhas:
        return analise.get("tipo", "Z2_LONGO")

    # 3) Claude — último recurso
    prompt = f"""Você é um especialista em treinamento de ciclismo MTB.

Atleta: Marciano, FC máxima 192 bpm
Zonas de FC: Z1 até 134 | Z2 135-153 | Z3 154-164 | Z4 165-177 | Z5 178+

Dados do treino:
{chr(10).join(linhas)}

Classifique o tipo de treino. Retorne APENAS uma das opções abaixo, sem explicação:
Z2_LONGO - aeróbico longo, foco em Z2 (base aeróbica, cadência, baixa intensidade)
TIROS - intervalos curtos de alta intensidade, sprints
VO2MAX - esforço alto sustentado, Z5 predominante
TEMPO - esforço moderado-alto contínuo, Z3-Z4 (limiar, sweet spot)
FORCA - força específica/torque: cadência baixa (45-60rpm) em subida ou marcha pesada
RECUPERACAO - sessão leve, Z1, recuperação ativa
DESCANSO - sem treino efetivo"""

    try:
        resp = await _client.messages.create(
            model=_MODEL,
            max_tokens=20,
            messages=[{"role": "user", "content": prompt}]
        )
        tipo = resp.content[0].text.strip().upper().split()[0]
        return tipo if tipo in _TIPOS_VALIDOS else analise.get("tipo", "Z2_LONGO")
    except Exception:
        return analise.get("tipo", "Z2_LONGO")


async def analisar_atividade_pos_treino(planejado: dict, resultado: dict, user_id: str | None = None, fit_path: str | None = None) -> dict:
    """Compara planejado vs realizado e retorna análise com pontos fortes e fracos.

    Se `fit_path` for fornecido, calcula o tempo real em cada zona de FC a partir
    do .fit — métrica muito mais fiel que a FC média para treinos de tiros."""
    linhas = []

    if planejado:
        linhas.append("PLANEJADO:")
        if planejado.get("tipo"):
            linhas.append(f"- Tipo: {planejado['tipo']}")
        if planejado.get("duracao_min"):
            linhas.append(f"- Duração: {planejado['duracao_min']} min")
        if planejado.get("cadencia_rpm"):
            linhas.append(f"- Cadência alvo: {planejado['cadencia_rpm']} rpm")
        if planejado.get("descricao"):
            linhas.append(f"- Descrição: {planejado['descricao']}")

    linhas.append("\nREALIZADO:")
    if resultado.get("duracao_min"):
        linhas.append(f"- Duração: {resultado['duracao_min']} min")
    if resultado.get("distancia_km"):
        linhas.append(f"- Distância: {resultado['distancia_km']} km")
    if resultado.get("avg_hr"):
        linhas.append(f"- FC média: {resultado['avg_hr']} bpm")
    if resultado.get("max_hr"):
        linhas.append(f"- FC máxima: {resultado['max_hr']} bpm")
    if resultado.get("cadencia_media_rpm"):
        linhas.append(f"- Cadência média: {resultado['cadencia_media_rpm']} rpm")
    if resultado.get("cadencia_max_rpm"):
        linhas.append(f"- Cadência máxima: {resultado['cadencia_max_rpm']} rpm")
    if resultado.get("elevacao_m"):
        linhas.append(f"- Elevação: {resultado['elevacao_m']} m")
    if resultado.get("calorias"):
        linhas.append(f"- Calorias: {resultado['calorias']} kcal")

    if not linhas:
        return _fallback_pos_treino(planejado, resultado)

    # Zonas reais configuradas (lidas do Garmin/tela), com defaults de segurança.
    try:
        from app.services.config_service import get_zonas, DEFAULT_ZONAS
        zc = await get_zonas(user_id) if user_id else dict(DEFAULT_ZONAS)
        zs = zc["zonas"]
        zonas_txt = " | ".join(f"Z{z['zona']} {z['min']}-{z['max']}" for z in zs)
        fc_max = zc.get("fc_max") or zs[-1]["max"]
        limiar = zc.get("limiar")
    except Exception:
        zonas_txt = "Z1 123-145 | Z2 146-158 | Z3 159-165 | Z4 166-177 | Z5 178-189"
        fc_max, limiar = 189, 172
        zs = [
            {"zona": 1, "min": 123, "max": 145}, {"zona": 2, "min": 146, "max": 158},
            {"zona": 3, "min": 159, "max": 165}, {"zona": 4, "min": 166, "max": 177},
            {"zona": 5, "min": 178, "max": 189},
        ]

    # Tempo real em cada zona de FC (lido do .fit, segundo-a-segundo). É o que
    # importa para julgar a intensidade de um treino de tiros — a FC média do
    # treino inteiro é diluída por aquecimento, recuperações e volta à calma.
    if fit_path:
        try:
            from app.services.fit_service import tempo_em_zonas
            tz = tempo_em_zonas(fit_path, zs)
            if tz:
                total = sum(tz.values()) or 1
                partes = []
                for z in zs:
                    secs = tz.get(z["zona"], 0)
                    if secs:
                        partes.append(f"Z{z['zona']} {secs/60:.0f}min ({round(secs*100/total)}%)")
                if partes:
                    linhas.append(f"- Tempo em cada zona de FC: {' | '.join(partes)}")
        except Exception:
            pass

    # Dados do atleta: nome/idade/peso do perfil do usuário (com defaults seguros)
    nome_atleta = "Atleta"
    idade_atleta: int | None = None
    peso_atleta: float | None = None
    objetivo_atleta = "melhorar performance MTB"
    if user_id:
        try:
            from app.services.user_service import get_por_id
            u = await get_por_id(user_id)
            if u:
                nome_atleta = u.get("nome") or "Atleta"
                perfil_u = u.get("perfil") or {}
                idade_atleta = perfil_u.get("idade") or None
                peso_atleta = perfil_u.get("peso_kg") or None
                pref_u = u.get("preferencias") or {}
                _OBJ_LABEL = {
                    "performance_mtb": "melhorar performance MTB (modelo polarizado)",
                    "aumentar_potencia": "aumentar potência e FTP",
                    "base_aerobica": "construir base aeróbica (volume Z2)",
                    "manter_performance": "manter a performance atual",
                    "emagrecimento": "emagrecer mantendo massa muscular e potência",
                }
                obj_key = pref_u.get("objetivo") or "performance_mtb"
                objetivo_atleta = _OBJ_LABEL.get(obj_key, obj_key)
        except Exception:
            pass  # mantém defaults genéricos

    idade_txt = f", {idade_atleta} anos" if idade_atleta else ""
    peso_txt = f", {peso_atleta:.0f} kg" if peso_atleta else ""
    lim_txt = f", limiar de lactato {limiar} bpm" if limiar else ""
    prompt = f"""Você é um coach de ciclismo MTB especializado em análise de desempenho.

Atleta: {nome_atleta}{idade_txt}{peso_txt}, FC máxima {fc_max} bpm{lim_txt}
Zonas de FC: {zonas_txt}
Objetivo: {objetivo_atleta}

{chr(10).join(linhas)}

DIRETRIZES DE ANÁLISE (fisiologia da FC — leve a sério):
- A FC tem resposta atrasada (lag): leva ~30-60s para subir até Z4/Z5 no início de
  um esforço forte e ~10-15s para baixar na recuperação. Os primeiros segundos de
  cada tiro saem de uma zona mais baixa — isso é normal, NÃO é falta de intensidade.
- Em treinos de TIROS, intervalados ou VO2MAX, NÃO julgue a intensidade pela FC
  MÉDIA do treino inteiro: ela é naturalmente baixa (Z1/Z2) porque inclui
  aquecimento, recuperações entre os tiros e volta à calma. Avalie a intensidade
  pela FC MÁXIMA atingida e pelo TEMPO EM ZONAS ALTAS (Z4/Z5), quando disponível.
- Nunca conclua que "faltou intensidade" só porque a FC média ficou em Z2 num
  treino de tiros — isso é esperado e correto.

Compare o planejado com o realizado. Comente intensidade (zonas de FC atingidas),
volume (duração realizada vs planejada), cadência e o que ajustar no próximo treino.
Seja CONCISO: cada ponto deve ter no máximo 1 frase curta (até ~140 caracteres),
sem markdown (não use **). No máximo 3 pontos fortes e 3 pontos fracos.
Atribua uma NOTA de 0 a 10 (pode ter 1 casa decimal) para o treino, ponderando os
pontos fortes e fracos: quão bem o realizado cumpriu o objetivo do planejado
(intensidade nas zonas certas, volume, cadência). 10 = execução exemplar;
abaixo de 5 só quando o treino destoou muito do planejado.
Responda APENAS em JSON válido, sem markdown, sem texto extra:
{{
  "nota": number (0 a 10, 1 casa decimal),
  "resumo": "string resumindo o treino em 1-2 frases objetivas",
  "pontos_fortes": ["até 3 pontos positivos, 1 frase cada"],
  "pontos_fracos": ["até 3 pontos a melhorar, 1 frase cada"]
}}"""

    try:
        resp = await _client.messages.create(
            model=_MODEL_ANALISE,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = resp.content[0].text.strip().replace("```json", "").replace("```", "").strip()
        data = json.loads(raw)
        return {
            "nota": _nota_valida(data.get("nota")),
            "resumo": data.get("resumo", ""),
            "pontos_fortes": data.get("pontos_fortes", []),
            "pontos_fracos": data.get("pontos_fracos", []),
        }
    except Exception:
        return _fallback_pos_treino(planejado, resultado)


def _nota_valida(valor) -> float | None:
    """Garante que a nota da IA caia em 0–10 (1 casa decimal); None se inválida."""
    try:
        n = round(float(valor), 1)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(10.0, n))


def _zona_de(bpm: int, zonas: list[dict]) -> int:
    """Número da zona em que um bpm cai (1-5)."""
    for z in zonas:
        if z["min"] <= bpm <= z["max"]:
            return z["zona"]
    return 5 if bpm > zonas[-1]["max"] else 1


def _fallback_pos_treino(planejado: dict, resultado: dict) -> dict:
    """Análise determinística (sem IA) a partir dos números do treino."""
    planejado = planejado or {}
    fortes, fracos = [], []

    dur = resultado.get("duracao_min")
    dist = resultado.get("distancia_km")
    avg = resultado.get("avg_hr")
    mx = resultado.get("max_hr")
    cad = resultado.get("cadencia_media_rpm")
    plan_dur = planejado.get("duracao_min")
    tipo = planejado.get("tipo")

    partes = []
    if dur:
        partes.append(f"{dur} min")
    if dist:
        partes.append(f"{dist} km")
    if avg:
        partes.append(f"FC média {avg} bpm")
    resumo = ("Treino registrado: " + ", ".join(partes) + ".") if partes else "Treino concluído."

    # volume realizado vs planejado
    if plan_dur and dur:
        if dur < plan_dur * 0.6:
            fracos.append(f"Volume bem abaixo do planejado ({dur} de {plan_dur} min) — sessão encurtada.")
        elif dur >= plan_dur * 0.9:
            fortes.append(f"Cumpriu o volume planejado ({dur}/{plan_dur} min).")

    # intensidade conforme o tipo de treino
    if avg is not None:
        if tipo in ("VO2MAX", "TIROS"):
            if (mx or 0) < 170:
                fracos.append(f"Para {tipo}, faltou intensidade: FC máx {mx or '—'} bpm não chegou na zona alta (Z4/Z5).")
            else:
                fortes.append(f"Atingiu intensidade alta (FC máx {mx} bpm), coerente com {tipo}.")
        elif tipo in ("RECUPERACAO", "Z2_LONGO"):
            if avg <= 158:
                fortes.append("Intensidade controlada, dentro do alvo aeróbico (Z1/Z2).")
            else:
                fracos.append(f"FC média {avg} bpm acima do ideal para {tipo} — manter mais leve.")

    # cadência
    if cad:
        if cad < 80:
            fracos.append(f"Cadência média baixa ({cad} rpm) — buscar 85-95 rpm na rodagem.")
        else:
            fortes.append(f"Boa cadência média ({cad} rpm).")

    if not fortes:
        fortes.append("Atividade registrada e sincronizada.")
    # Nota determinística: parte de 7 e pondera pontos fortes contra fracos.
    nota = max(0.0, min(10.0, round(7.0 + len(fortes) - 1.5 * len(fracos), 1)))
    return {"nota": nota, "resumo": resumo, "pontos_fortes": fortes, "pontos_fracos": fracos}


async def gerar_focos_prova(user_id: str, prova: dict, fase: str = "",
                            dias_restantes: int | None = None) -> list[str]:
    """Até 3 focos de melhoria até a prova, a partir das últimas avaliações de
    treino do atleta + as exigências da prova. Fallback determinístico se a IA
    estiver indisponível ou não houver dados suficientes."""
    from app.services.mongo_service import get_db

    db = get_db()
    docs = await db.semanas.find({"user_id": str(user_id)}).sort("semana_inicio", -1).to_list(length=8)

    avals: list[tuple] = []  # (data, tipo, nota, pontos_fracos)
    for doc in docs:
        for t in doc.get("treinos", []):
            ia = (t.get("resultado") or {}).get("analise_ia")
            if ia and ia.get("pontos_fracos"):
                avals.append((t.get("data") or "", t.get("tipo") or "", ia.get("nota"), ia.get("pontos_fracos")))
    avals.sort(key=lambda x: x[0], reverse=True)
    avals = avals[:6]

    fracos_recentes: list[str] = [f for (_, _, _, fr) in avals for f in fr]
    if not fracos_recentes:
        return []

    # Fallback determinístico: pontos fracos recentes distintos (preserva ordem).
    def _fallback() -> list[str]:
        vistos, out = set(), []
        for f in fracos_recentes:
            chave = f.lower()[:40]
            if chave not in vistos:
                vistos.add(chave)
                out.append(f)
            if len(out) >= 3:
                break
        return out

    linhas_aval = "\n".join(
        f"- {data} ({tipo}, nota {nota if nota is not None else '—'}): " + "; ".join(fr)
        for (data, tipo, nota, fr) in avals
    )
    prova_txt = (
        f"Nome: {prova.get('nome','')}\n"
        f"Data: {prova.get('data','')}"
        + (f" (faltam {dias_restantes} dias)" if dias_restantes is not None else "")
        + (f"\nFase atual de treino: {fase}" if fase else "")
        + (f"\nDistância: {prova['distancia_km']} km" if prova.get("distancia_km") else "")
        + (f"\nAltimetria: {prova['altimetria_m']} m" if prova.get("altimetria_m") else "")
        + (f"\nTerreno: {prova['terreno']}" if prova.get("terreno") else "")
        + (f"\nMeta: {prova['meta']}" if prova.get("meta") else "")
    )

    prompt = f"""Você é um coach de ciclismo MTB. Com base nas exigências da prova-alvo
e nos pontos fracos recorrentes dos treinos recentes do atleta, defina os focos de
melhoria mais importantes ATÉ o dia da prova.

PROVA-ALVO:
{prova_txt}

PONTOS FRACOS DOS TREINOS RECENTES:
{linhas_aval}

Gere NO MÁXIMO 3 focos objetivos e acionáveis (1 frase curta cada, até ~120
caracteres, sem markdown), priorizando o que mais impacta o desempenho NESTA prova.
Responda APENAS em JSON válido, sem markdown:
{{"focos": ["foco 1", "foco 2", "foco 3"]}}"""

    try:
        resp = await _client.messages.create(
            model=_MODEL,
            max_tokens=250,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = resp.content[0].text.strip().replace("```json", "").replace("```", "").strip()
        data = json.loads(raw)
        focos = [str(f).strip() for f in (data.get("focos") or []) if str(f).strip()]
        return focos[:3] or _fallback()
    except Exception:
        return _fallback()


async def gerar_plano_alimentar(treino: Treino | None = None) -> PlanoAlimentar:
    prompt = build_prompt(treino)
    resp = await _client.messages.create(
        model=_MODEL,
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = resp.content[0].text.strip().replace("```json", "").replace("```", "").strip()
    data = json.loads(raw)
    return PlanoAlimentar(
        data=datetime.now(),
        treino=treino,
        tipo_dia=data["tipo_dia"],
        kcal_total=data["kcal_total"],
        proteina_total_g=data["proteina_total_g"],
        refeicoes=data["refeicoes"]
    )


async def extrair_zonas_de_imagem(image_bytes: bytes, mime_type: str) -> dict:
    """Lê uma captura de tela das zonas de FC do Garmin e extrai as faixas.

    Retorna {"fc_max", "limiar", "zonas": [{"zona","min","max"}, ...]}.
    Levanta exceção se não conseguir interpretar.
    """
    prompt = """Analise esta captura de tela das ZONAS DE FREQUÊNCIA CARDÍACA de um relógio ou app Garmin.

Extraia, em batimentos por minuto (bpm):
- O valor MÍNIMO e MÁXIMO de cada zona (Z1 a Z5).
- A FC máxima (FCmáx) e o limiar de lactato, se aparecerem na tela.

Regras:
- Sempre devolva exatamente 5 zonas (zona 1 a 5), em ordem crescente.
- Se uma zona mostrar só o limite inferior (ex.: "> 177" ou "177+"), use esse número como "min" e a FC máxima (ou 200 se não houver) como "max".
- Se a zona 1 não mostrar mínimo, use um valor razoável (ex.: 50% da FCmáx).
- Os números devem ser inteiros.

Responda APENAS em JSON válido, sem markdown, sem texto extra:
{"fc_max": number ou null, "limiar": number ou null, "zonas": [{"zona": 1, "min": number, "max": number}, {"zona": 2, ...}, {"zona": 3, ...}, {"zona": 4, ...}, {"zona": 5, ...}]}"""

    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    content = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": mime_type,
                "data": image_b64,
            },
        },
        {"type": "text", "text": prompt},
    ]

    resp = await _client.messages.create(
        model=_MODEL,
        max_tokens=300,
        messages=[{"role": "user", "content": content}]
    )
    raw = resp.content[0].text.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(raw)


async def estimar_alimento_extra(texto: str | None = None,
                                 image_bytes: bytes | None = None,
                                 mime_type: str | None = None) -> dict:
    """Estima calorias e proteína de algo comido fora do plano, a partir de uma
    descrição em texto e/ou de uma foto do alimento.

    Retorna {"resumo": str, "kcal": int, "proteina_g": float}.
    Levanta QuotaExcedida se a API estiver indisponível.
    """
    prompt = (
        "Você é um nutricionista. Estime o TOTAL de calorias (kcal) e de proteína "
        "(g) do que a pessoa comeu/bebeu FORA do plano, descrito abaixo e/ou na "
        "imagem. Considere porções típicas brasileiras.\n"
    )
    if texto:
        prompt += f'\nDescrição do que comeu: "{texto}"\n'
    prompt += (
        '\nResponda APENAS em JSON válido, sem markdown:\n'
        '{"resumo": "breve descrição do que foi consumido", "kcal": number, "proteina_g": number}'
    )

    content: list = []
    if image_bytes and mime_type:
        image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": mime_type,
                "data": image_b64,
            },
        })
    content.append({"type": "text", "text": prompt})

    try:
        resp = await _client.messages.create(
            model=_MODEL,
            max_tokens=150,
            messages=[{"role": "user", "content": content}]
        )
        raw = resp.content[0].text.strip().replace("```json", "").replace("```", "").strip()
        d = json.loads(raw)
        return {
            "resumo": str(d.get("resumo") or (texto or "Alimento fora do plano")),
            "kcal": max(0, int(round(float(d.get("kcal") or 0)))),
            "proteina_g": max(0.0, round(float(d.get("proteina_g") or 0), 1)),
        }
    except Exception as e:
        raise QuotaExcedida() from e


async def interpretar_mensagem(texto: str, referencia_datas: str) -> dict:
    """Classifica a intenção de uma mensagem de WhatsApp do ciclista e extrai os
    dados. Retorna um dict com os campos relevantes para a intenção detectada.

    intencao ∈ plano_dia | treino_dia | registrar_fuga | trocar_alimento |
               alterar_treino | criar_treino | remover_treino | conversa

    Campos comuns:
      intencao, data (ISO YYYY-MM-DD), resposta (só conversa)

    Campos adicionais por intenção:
      alterar_treino: data_destino (ISO YYYY-MM-DD)
      criar_treino:   duracao_min (int), tipo (Z2_LONGO|TIROS|VO2MAX|TEMPO|FORCA|RECUPERACAO), descricao
      registrar_fuga: descricao
      trocar_alimento: de, para
    """
    prompt = f"""Você é o assistente de nutrição e treino de um ciclista de MTB, conversando pelo WhatsApp (responda sempre em português do Brasil, tom amigável e direto).

Classifique a mensagem do usuário em UMA intenção e extraia os dados.

Datas de referência (use EXATAMENTE estas datas para resolver "hoje", "amanhã", "quinta", etc. — NÃO invente datas):
{referencia_datas}

Intenções disponíveis:
- "plano_dia": quer saber a alimentação/cardápio/refeições de um dia.
- "treino_dia": quer saber o treino/pedal de um dia.
- "registrar_fuga": disse que comeu ou bebeu algo (fora do plano).
- "trocar_alimento": quer trocar um alimento do cardápio por outro.
- "alterar_treino": quer MOVER/TRANSFERIR/ALTERAR o treino de um dia para outro dia. Ex.: "muda o treino de sábado pra sexta", "altera o treino de quinta para quarta". Extraia o dia de ORIGEM em "data" e o dia de DESTINO em "data_destino" (ambos ISO YYYY-MM-DD).
- "criar_treino": quer CRIAR/ADICIONAR um treino novo em um dia. Ex.: "cria um treino for fun no sábado de 3 horas", "adiciona um pedal de recuperação na sexta de 1h30". Extraia: "data" (o dia), "duracao_min" (duração em minutos — "três horas"=180, "1h30"=90, "90 min"=90, "2h"=120), "tipo" (um dos valores abaixo inferido da descrição) e "descricao" (texto livre do que o usuário pediu).
- "remover_treino": quer REMOVER/EXCLUIR/DELETAR/CANCELAR/TIRAR o treino de um dia (deixar o dia de descanso). Ex.: "remove o treino de amanhã", "exclui o treino de sábado", "cancela o pedal de domingo", "tira o treino de quinta". Extraia o dia em "data" (ISO YYYY-MM-DD). NÃO confunda com alterar_treino: aqui NÃO há dia de destino.
- "conversa": saudação, dúvida geral ou qualquer coisa que não se encaixe acima.

Regras para inferir o tipo de treino em "criar_treino":
  - "for fun" / "passeio" / "longo" / sem especificar → "Z2_LONGO"
  - "recuperação" / "leve" / "regenerativo" → "RECUPERACAO"
  - "tiros" / "intervalado" / "sprint" → "TIROS"
  - "vo2" / "vo2max" / "máxima intensidade" → "VO2MAX"
  - "tempo" / "ritmo" / "limiar" → "TEMPO"
  - "força" / "força específica" / "cadência baixa" → "FORCA"
  - NUNCA use "DESCANSO" para criar_treino.

Responda APENAS em JSON válido, sem markdown, sem explicações extras:
{{"intencao":"...", "data":"YYYY-MM-DD ou null", "data_destino":"YYYY-MM-DD ou null — só alterar_treino", "duracao_min":null, "tipo":null, "descricao":"o que comeu (registrar_fuga) ou descrição do treino (criar_treino) — null se não se aplica", "de":"alimento trocado — só trocar_alimento — null se não", "para":"alimento novo — só trocar_alimento — null se não", "resposta":"resposta curta e útil — só quando intencao=conversa — null se não"}}

Mensagem do usuário: "{texto}"
"""

    try:
        resp = await _client.messages.create(
            model=_MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = resp.content[0].text.strip().replace("```json", "").replace("```", "").strip()
        d = json.loads(raw)
        d.setdefault("intencao", "conversa")
        return d
    except Exception as e:
        raise QuotaExcedida() from e


async def interpretar_ajuste_cardapio(historico: list[dict], mensagem: str) -> dict:
    """Interpreta uma mensagem do chat de ajuste do cardápio (tela /nutrition/chat),
    dado o histórico recente da conversa. O usuário quer mudar a quantidade de um
    alimento (ou categoria, ex. "arroz") no cardápio fixo dele — de forma
    permanente, não só pro dia de hoje.

    Retorna {"resposta": str, "acao": dict | None}.
    "acao", quando preenchida, é um dos formatos:
      {"tipo": "definir_porcoes", "escopo": "alimento"|"categoria", "chave": str,
       "porcoes": number, "refeicao": str | None}
      {"tipo": "remover_ajuste", "escopo": "alimento"|"categoria", "chave": str,
       "refeicao": str | None}
    "acao" só vem preenchida quando o pedido já está claro (alimento/categoria e
    quantidade definidos) — senão vem None e "resposta" pergunta o que falta.

    Levanta QuotaExcedida se a API estiver indisponível.
    """
    from app.services.nutricao_service import ALIMENTOS, categorias_alimentos, nomes_refeicoes

    alimentos_lista = "\n".join(f"- {chave}: {info['nome']}" for chave, info in ALIMENTOS.items())
    categorias_lista = ", ".join(sorted(set(categorias_alimentos().values())))
    refeicoes_lista = ", ".join(nomes_refeicoes())
    historico_txt = "\n".join(
        f"{'Usuário' if m['role'] == 'user' else 'Assistente'}: {m['texto']}" for m in historico[-10:]
    ) or "(sem mensagens anteriores)"

    prompt = f"""Você é o assistente de nutrição de um app de treino MTB, conversando com o usuário numa tela de chat dedicada a ajustar o cardápio fixo dele (responda sempre em português do Brasil, tom amigável e direto).

O cardápio é montado por um motor fixo a partir de uma tabela de alimentos — cada refeição escolhe alimentos em porções (ex.: 2,5 porções de arroz = 10 colheres de sopa, já que 1 porção = 100g = 4 colheres). O usuário quer DISCUTIR e AJUSTAR PERMANENTEMENTE a quantidade de um alimento ou categoria no cardápio dele (não é um ajuste só de hoje).

Alimentos disponíveis (chave: nome):
{alimentos_lista}

Categorias (agrupam alimentos parecidos, ex. "arroz" agrupa arroz branco e integral): {categorias_lista}

Nomes de refeição válidos: {refeicoes_lista}

Histórico recente da conversa:
{historico_txt}

Nova mensagem do usuário: "{mensagem}"

Decida:
1. Se o usuário já deixou claro QUAL alimento/categoria, QUANTAS porções quer (ou que quer remover um ajuste anterior e voltar ao padrão), e opcionalmente EM QUAL refeição — preencha "acao".
   - "porcoes" é a quantidade de porções-base (ex.: 0.5 porção de arroz = 2 colheres; 1 porção = 4 colheres). Se o usuário falar em colheres, converta (1 porção de arroz/aveia = 4 colheres de sopa).
   - Se ele não especificar a refeição, "refeicao" é null (vale em qualquer refeição que tenha esse alimento).
   - Se ele pedir pra "voltar ao normal"/"desfazer"/"tirar esse ajuste", use "tipo":"remover_ajuste".
2. Se faltar informação pra agir com segurança (ex.: não disse quanto quer, ou o alimento citado é ambíguo), deixe "acao" como null e pergunte o que falta em "resposta".
3. Trocar um alimento por outro (ex. arroz por batata-doce) ou excluir um alimento da rotação NÃO é suportado aqui — se o usuário pedir isso, explique em "resposta" que esse pedido específico deve ser feito pelo assistente do WhatsApp, e deixe "acao" null.

Responda APENAS em JSON válido, sem markdown:
{{"resposta": "texto curto pra mostrar ao usuário", "acao": null ou {{"tipo": "definir_porcoes" ou "remover_ajuste", "escopo": "alimento" ou "categoria", "chave": "...", "porcoes": number (omitir se tipo=remover_ajuste), "refeicao": "..." ou null}}}}
"""

    try:
        resp = await _client.messages.create(
            model=_MODEL,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = resp.content[0].text.strip().replace("```json", "").replace("```", "").strip()
        d = json.loads(raw)
        return {"resposta": str(d.get("resposta") or ""), "acao": d.get("acao") or None}
    except Exception as e:
        raise QuotaExcedida() from e


class QuotaExcedida(Exception):
    """API de IA indisponível (rate limit, erro de rede, parse inválido)."""


def _e_cota(e: Exception) -> bool:
    """Retorna True se o erro é de rate limit da API."""
    s = str(e).lower()
    return any(t in s for t in ("429", "rate_limit", "rate limit", "quota", "exceeded", "exhaust"))
