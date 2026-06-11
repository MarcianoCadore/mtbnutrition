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
        from app.services.config_service import get_zonas
        zc = await get_zonas()
        zs = zc["zonas"]
        zonas_txt = " | ".join(f"Z{z['zona']} {z['min']}-{z['max']}" for z in zs)
        fc_max = zc.get("fc_max") or zs[-1]["max"]
        limiar = zc.get("limiar")
    except Exception:
        zonas_txt = "Z1 123-145 | Z2 146-158 | Z3 159-165 | Z4 166-177 | Z5 178-189"
        fc_max, limiar = 189, 172

    lim_txt = f", limiar de lactato {limiar} bpm" if limiar else ""
    prompt = f"""Você é um coach de ciclismo MTB especializado em análise de desempenho.

Atleta: Marciano, 34 anos, FC máxima {fc_max} bpm{lim_txt}
Zonas de FC: {zonas_txt}
Objetivo: emagrecer preservando músculo + melhorar performance MTB

{chr(10).join(linhas)}

Compare o planejado com o realizado. Comente intensidade (zonas de FC atingidas),
volume (duração realizada vs planejada), cadência e o que ajustar no próximo treino.
Responda APENAS em JSON válido, sem markdown, sem texto extra:
{{
  "resumo": "string resumindo o treino em 1-2 frases objetivas",
  "pontos_fortes": ["lista de pontos positivos observados"],
  "pontos_fracos": ["lista de pontos a melhorar"]
}}"""

    modelos = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.0-flash"]

    def _call():
        ultimo_erro = None
        for nome in modelos:
            try:
                modelo = genai.GenerativeModel(nome)
                resp = modelo.generate_content(prompt)
                raw = resp.text.strip().replace("```json", "").replace("```", "").strip()
                data = json.loads(raw)
                return {
                    "resumo": data.get("resumo", ""),
                    "pontos_fortes": data.get("pontos_fortes", []),
                    "pontos_fracos": data.get("pontos_fracos", []),
                }
            except Exception as e:
                ultimo_erro = e
                if _e_cota(e):
                    continue
                raise
        raise QuotaExcedida() from ultimo_erro

    try:
        import asyncio
        return await asyncio.to_thread(_call)
    except Exception:
        # IA indisponível (cota, parse, rede): análise determinística pelos números.
        return _fallback_pos_treino(planejado, resultado)


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
    return {"resumo": resumo, "pontos_fortes": fortes, "pontos_fracos": fracos}


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


async def extrair_zonas_de_imagem(image_bytes: bytes, mime_type: str) -> dict:
    """Lê uma captura de tela das zonas de FC do Garmin e extrai as faixas.

    Retorna {"fc_max", "limiar", "zonas": [{"zona","min","max"}, ...]}.
    Usa o Gemini em modo visão. Levanta exceção se não conseguir interpretar.
    """
    import asyncio

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

    imagem = {"mime_type": mime_type, "data": image_bytes}

    # Modelos de visão em ordem de preferência. Cada modelo tem cota gratuita
    # própria, então se um estourar (429) tentamos o próximo.
    modelos = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.0-flash"]

    def _call():
        ultimo_erro = None
        for nome in modelos:
            try:
                modelo = genai.GenerativeModel(nome)
                resp = modelo.generate_content([prompt, imagem])
                raw = resp.text.strip().replace("```json", "").replace("```", "").strip()
                return json.loads(raw)
            except Exception as e:
                ultimo_erro = e
                if _e_cota(e):
                    continue   # cota desse modelo esgotada — tenta o próximo
                raise          # outro erro: propaga de imediato
        # todos os modelos sem cota
        raise QuotaExcedida() from ultimo_erro

    return await asyncio.to_thread(_call)


class QuotaExcedida(Exception):
    """Cota gratuita do Gemini esgotada em todos os modelos de visão."""


def _e_cota(e: Exception) -> bool:
    s = str(e).lower()
    return any(t in s for t in ("429", "quota", "exceeded", "exhaust", "rate limit"))
