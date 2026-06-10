import google.generativeai as genai
import json
import re
from config.settings import settings
from app.models.models import Treino, TipoTreino, PlanoAlimentar
from datetime import datetime

genai.configure(api_key=settings.GEMINI_API_KEY)
client = genai.GenerativeModel("gemini-2.5-flash-lite")

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
# Classificador determinístico — não depende da quota do Gemini.
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
      3. Gemini (último recurso — sujeito a quota)
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

    # 3) Gemini — último recurso
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
        response = client.generate_content(prompt)
        tipo = response.text.strip().upper().split()[0]
        return tipo if tipo in _TIPOS_VALIDOS else analise.get("tipo", "Z2_LONGO")
    except Exception:
        return analise.get("tipo", "Z2_LONGO")


async def analisar_atividade_pos_treino(planejado: dict, resultado: dict) -> dict:
    """Compara planejado vs realizado e retorna análise com pontos fortes e fracos."""
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
    if resultado.get("elevacao_m"):
        linhas.append(f"- Elevação: {resultado['elevacao_m']} m")
    if resultado.get("calorias"):
        linhas.append(f"- Calorias: {resultado['calorias']} kcal")

    if not linhas:
        return {"resumo": "Treino concluído.", "pontos_fortes": [], "pontos_fracos": []}

    prompt = f"""Você é um coach de ciclismo MTB especializado em análise de desempenho.

Atleta: Marciano, 34 anos, 85kg, FC máxima 192 bpm
Zonas de FC: Z1 até 134 | Z2 135-153 | Z3 154-164 | Z4 165-177 | Z5 178+
Objetivo: emagrecer preservando músculo + melhorar performance MTB

{chr(10).join(linhas)}

Analise o treino e responda APENAS em JSON válido, sem markdown, sem texto extra:
{{
  "resumo": "string resumindo o treino em 1-2 frases objetivas",
  "pontos_fortes": ["lista de pontos positivos observados"],
  "pontos_fracos": ["lista de pontos a melhorar"]
}}"""

    try:
        response = client.generate_content(prompt)
        raw = response.text.strip().replace("```json", "").replace("```", "").strip()
        data = json.loads(raw)
        return {
            "resumo": data.get("resumo", ""),
            "pontos_fortes": data.get("pontos_fortes", []),
            "pontos_fracos": data.get("pontos_fracos", []),
        }
    except Exception:
        return {"resumo": "Treino concluído.", "pontos_fortes": ["Atividade registrada"], "pontos_fracos": []}


async def gerar_plano_alimentar(treino: Treino | None = None) -> PlanoAlimentar:
    prompt = build_prompt(treino)
    response = client.generate_content(prompt)
    raw = response.text.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    data = json.loads(raw)
    return PlanoAlimentar(
        data=datetime.now(),
        treino=treino,
        tipo_dia=data["tipo_dia"],
        kcal_total=data["kcal_total"],
        proteina_total_g=data["proteina_total_g"],
        refeicoes=data["refeicoes"]
    )
