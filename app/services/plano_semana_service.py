"""Geração da próxima semana de treinos usando IA (Gemini)."""

import json
import logging
from datetime import datetime, timedelta

import google.generativeai as genai

from config.settings import settings
from app.services.mongo_service import get_db

logger = logging.getLogger(__name__)

genai.configure(api_key=settings.GEMINI_API_KEY)
_client = genai.GenerativeModel("gemini-2.5-flash-lite")

_TIPOS_VALIDOS = {"Z2_LONGO", "TIROS", "VO2MAX", "TEMPO", "FORCA", "RECUPERACAO", "DESCANSO"}

_DURACAO_PADRAO = {
    "Z2_LONGO":    120,
    "TEMPO":        70,
    "FORCA":        65,
    "TIROS":        62,
    "VO2MAX":       62,
    "RECUPERACAO":  55,
    "DESCANSO":      0,
}

_DURACAO_MAXIMA = {
    "Z2_LONGO":    150,
    "TEMPO":        90,
    "FORCA":        90,
    "TIROS":        80,
    "VO2MAX":       80,
    "RECUPERACAO":  75,
}

_DESCRICAO_PADRAO = {
    "Z2_LONGO":    "Base aeróbica Z2. FC 146-158 bpm, cadência 85-95 rpm.",
    "TEMPO":       "3x10 min Z3 (159-165 bpm), recuperação Z2.",
    "FORCA":       "4x6 min Z3 cadência baixa (50-60 rpm), recuperação Z2.",
    "TIROS":       "8x30s Z5 (>177 bpm) com 3.5 min recuperação Z1.",
    "VO2MAX":      "4x4 min Z5 (>177 bpm) com 4 min recuperação Z2.",
    "RECUPERACAO": "Pedal leve Z1 (<145 bpm). Recuperação ativa.",
    "DESCANSO":    "",
}


def _proxima_semana(semana_atual: str) -> str:
    d = datetime.strptime(semana_atual, "%Y-%m-%d").date()
    return (d + timedelta(days=7)).isoformat()


def _shift_data(data_iso: str, delta_dias: int) -> str:
    d = datetime.strptime(data_iso, "%Y-%m-%d").date()
    return (d + timedelta(days=delta_dias)).isoformat()


# ── Regras fixas de agenda do Marciano (ele trabalha de seg a sex) ────────────
_MAX_MIN_DIA_UTIL = 120   # seg–sex: nenhum treino acima de 2h
_LONGAO_SABADO_MIN = 180  # sábado: sempre um longão de 3h (Z2 / "for fun")
_LONGAO_SABADO_DESC = "Longão for fun (~3h) — base aeróbica Z2, ritmo livre/conversacional. Foco em volume e economia de pedalada."


def _aplicar_regras_agenda(data_iso: str, tipo: str, duracao, descricao, cadencia):
    """Aplica as regras de agenda fixas, sobrepondo o que a IA/fallback gerou:
    - segunda a sexta: nenhum treino acima de 120 min (dia de trabalho);
    - sábado: SEMPRE um longão de 180 min (Z2, pode ser "for fun");
    - domingo: livre (não mexe — geralmente descanso/recuperação).
    Retorna (tipo, duracao, descricao, cadencia) ajustados.
    """
    try:
        wd = datetime.strptime(data_iso, "%Y-%m-%d").weekday()  # 0=seg ... 6=dom
    except (ValueError, TypeError):
        return tipo, duracao, descricao, cadencia

    if wd == 5:  # sábado → longão de 3h garantido
        return "Z2_LONGO", _LONGAO_SABADO_MIN, _LONGAO_SABADO_DESC, (cadencia or "85-95")

    if wd <= 4 and tipo != "DESCANSO" and duracao:  # seg–sex → teto de 2h
        duracao = min(int(duracao), _MAX_MIN_DIA_UTIL)

    return tipo, duracao, descricao, cadencia


def _resumo_treino(t: dict) -> str:
    linhas = [f"  - {t['data']} | {t.get('tipo','?')}"]
    if t.get("duracao_min"):
        linhas.append(f"    Duração: {t['duracao_min']} min")
    res = t.get("resultado") or {}
    ia = res.get("analise_ia") or {}
    if res.get("avg_hr"):
        linhas.append(f"    FC média: {res['avg_hr']} bpm")
    if res.get("distancia_km"):
        linhas.append(f"    Distância: {res['distancia_km']} km")
    if ia.get("resumo"):
        linhas.append(f"    Análise: {ia['resumo']}")
    if ia.get("pontos_fortes"):
        linhas.append(f"    Pontos fortes: {'; '.join(ia['pontos_fortes'])}")
    if ia.get("pontos_fracos"):
        linhas.append(f"    A melhorar: {'; '.join(ia['pontos_fracos'])}")
    return "\n".join(linhas)


async def gerar_proxima_semana(user_id: str, semana_atual: str) -> dict:
    """Gera o plano da próxima semana com base na análise da semana atual."""
    db = get_db()
    doc = await db.semanas.find_one({"semana_inicio": semana_atual, "user_id": user_id})
    if not doc:
        raise ValueError(f"Semana {semana_atual} não encontrada")

    treinos = doc.get("treinos", [])
    proxima = _proxima_semana(semana_atual)

    resumos = "\n".join(_resumo_treino(t) for t in treinos if t.get("tipo") != "DESCANSO")
    if not resumos:
        resumos = "  (nenhum treino com dados registrados)"

    prompt = f"""Você é um coach de ciclismo MTB especializado em periodização progressiva.

ATLETA: Marciano, 34 anos, 85 kg, meta: emagrecer + melhorar performance MTB.
FCMÁX: 190 bpm | Limiar de lactato: 172 bpm
ZONAS GARMIN: Z1 <145 | Z2 146-158 | Z3 159-165 | Z4 166-177 | Z5 >177

SEMANA ATUAL ({semana_atual}):
{resumos}

DISTRIBUIÇÃO ATUAL DOS TREINOS:
{chr(10).join(f"  {t['data']} → {t.get('tipo','DESCANSO')}" for t in treinos)}

RESTRIÇÕES DE AGENDA (OBRIGATÓRIAS — o atleta trabalha de segunda a sexta):
- Segunda a sexta: NENHUM treino acima de 120 min (2h). Sessões de qualidade cabem em 2h.
- Sábado: SEMPRE um longão de 180 min (3h), Z2_LONGO ("for fun", ritmo livre/base aeróbica). É o maior treino da semana.
- Domingo: livre — priorize DESCANSO ou RECUPERAÇÃO leve para absorver a carga do sábado.

PRIORIZE GANHO DE PERFORMANCE (modelo polarizado):
- No máximo 2 dias DUROS na semana (ex.: VO2MAX e TIROS, ou VO2MAX e TEMPO), bem ESPAÇADOS (não em dias seguidos).
- Dias fáceis (Z2/RECUPERACAO) devem ser REALMENTE fáceis (FC baixa, Z2 puro) para recuperar — evite a "zona cinza" (treinar sempre em intensidade média).
- Garanta recuperação suficiente: pelo menos 1 dia de descanso/recuperação entre blocos duros.
- Os dias DUROS rendem mais descansados — não coloque dois dias pesados grudados nem antes do longão de sábado.

REGRAS DE PROGRESSÃO:
- Aumentar volume (+5-10% em duracao_min) quando a semana foi bem executada, respeitando o teto de 120 min em dias úteis.
- Manter ou reduzir se houve dificuldades (pontos fracos > pontos fortes).
- DESCANSO permanece DESCANSO nos mesmos dias.
- Para TIROS: aumentar número de repetições (8→10→12) antes de aumentar duração.
- Para VO2MAX: aumentar reps (4→5) antes de aumentar a duração dos blocos.

Responda APENAS em JSON válido, sem markdown, sem texto extra:
{{
  "analise_semana": "string com avaliação da semana atual em 2-3 frases",
  "progressao": "string descrevendo o que vai mudar na próxima semana",
  "treinos": [
    {{
      "data": "YYYY-MM-DD",
      "tipo": "TIPO",
      "duracao_min": 90,
      "descricao": "texto descritivo para aparecer no Edge 830",
      "cadencia_rpm": "85-95"
    }}
  ]
}}

Os dados de "treinos" devem ter exatamente 7 entradas (uma por dia da semana {proxima} a {_shift_data(proxima, 6)}).
"""

    try:
        response = _client.generate_content(prompt)
        raw = response.text.strip().replace("```json", "").replace("```", "").strip()
        data = json.loads(raw)
    except Exception as e:
        logger.warning("Gemini falhou para gerar próxima semana: %s — usando fallback", e)
        data = _fallback(treinos, proxima)

    # normaliza e valida cada treino retornado pela IA
    treinos_out = []
    for t in data.get("treinos", []):
        tipo = (t.get("tipo") or "DESCANSO").upper()
        if tipo not in _TIPOS_VALIDOS:
            tipo = "DESCANSO"
        duracao = int(t.get("duracao_min") or _DURACAO_PADRAO.get(tipo, 60))
        duracao = min(duracao, _DURACAO_MAXIMA.get(tipo, 150))
        descricao = t.get("descricao") or _DESCRICAO_PADRAO.get(tipo, "")
        cadencia = t.get("cadencia_rpm")
        # regras de agenda (teto de 2h em dia útil, longão de 3h no sábado)
        tipo, duracao, descricao, cadencia = _aplicar_regras_agenda(
            t.get("data", ""), tipo, duracao, descricao, cadencia)
        treinos_out.append({
            "data":        t.get("data", ""),
            "tipo":        tipo,
            "duracao_min": duracao if tipo != "DESCANSO" else None,
            "descricao":   descricao,
            "cadencia_rpm": cadencia,
        })

    return {
        "semana_proxima": proxima,
        "analise_semana": data.get("analise_semana", ""),
        "progressao":     data.get("progressao", ""),
        "treinos":        treinos_out,
    }


def _fallback(treinos_atuais: list, proxima: str) -> dict:
    """Progressão determinística (+5% duração) quando Gemini não está disponível."""
    novos = []
    for t in treinos_atuais:
        tipo = t.get("tipo", "DESCANSO")
        dur = t.get("duracao_min") or _DURACAO_PADRAO.get(tipo, 60)
        if tipo != "DESCANSO" and dur:
            dur = min(int(dur * 1.05), 150)
        data_nova = _shift_data(t["data"], 7)
        descricao = t.get("descricao") or _DESCRICAO_PADRAO.get(tipo, "")
        cadencia = t.get("cadencia_rpm")
        # regras de agenda (teto de 2h em dia útil, longão de 3h no sábado)
        tipo, dur, descricao, cadencia = _aplicar_regras_agenda(
            data_nova, tipo, dur, descricao, cadencia)
        novos.append({
            "data":        data_nova,
            "tipo":        tipo,
            "duracao_min": dur if tipo != "DESCANSO" else None,
            "descricao":   descricao,
            "cadencia_rpm": cadencia,
        })
    return {
        "analise_semana": "Gemini indisponível — progressão automática de +5% aplicada.",
        "progressao": "Duração de cada treino aumentada em 5%.",
        "treinos": novos,
    }
