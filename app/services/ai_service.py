import google.generativeai as genai
import json
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
Meta proteína: 187g/dia | Não gosta de whey protein

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

_TIPOS_VALIDOS = {"Z2_LONGO", "TIROS", "VO2MAX", "TEMPO", "RECUPERACAO", "DESCANSO"}

async def classificar_tipo_treino(analise: dict) -> str:
    """Usa IA para classificar o tipo de treino com base nos dados do .fit."""
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

    prompt = f"""Você é um especialista em treinamento de ciclismo MTB.

Atleta: Marciano, FC máxima 192 bpm
Zonas de FC: Z1 até 134 | Z2 135-153 | Z3 154-164 | Z4 165-177 | Z5 178+

Dados do treino:
{chr(10).join(linhas)}

Classifique o tipo de treino. Retorne APENAS uma das opções abaixo, sem explicação:
Z2_LONGO - aeróbico longo, foco em Z2 (base aeróbica, cadência, baixa intensidade)
TIROS - intervalos curtos de alta intensidade, sprints
VO2MAX - esforço alto sustentado, Z5 predominante
TEMPO - esforço moderado-alto contínuo, Z3-Z4
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
