"""Geração da próxima semana de treinos usando IA (Gemini)."""

import json
import logging
from datetime import datetime, timedelta

from google import genai as _genai_sdk

from config.settings import settings
from app.services.mongo_service import get_db
from app.services.user_service import get_por_id

logger = logging.getLogger(__name__)


class _GeminiClient:
    """Thin wrapper preserving the .generate_content(prompt) interface."""

    def __init__(self, model: str):
        self._sdk = _genai_sdk.Client(api_key=settings.GEMINI_API_KEY)
        self._model = model

    def generate_content(self, prompt: str):
        return self._sdk.models.generate_content(model=self._model, contents=prompt)


_client = _GeminiClient("gemini-2.5-flash-lite")

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


_INSTRUCOES_OBJETIVO = {
    "performance_mtb": """OBJETIVO — PERFORMANCE MTB (modelo polarizado):
- No máximo 2 dias DUROS na semana (ex.: VO2MAX e TIROS, ou VO2MAX e TEMPO), bem ESPAÇADOS (não em dias seguidos).
- Dias fáceis (Z2/RECUPERACAO) devem ser REALMENTE fáceis (FC baixa, Z2 puro) — evite a "zona cinza".
- Garanta recuperação: pelo menos 1 dia de descanso/recuperação entre blocos duros.
- Os dias DUROS rendem mais descansados — nunca dois dias pesados grudados nem antes do longão.""",

    "aumentar_potencia": """OBJETIVO — AUMENTAR POTÊNCIA / FTP:
- Priorize 2 sessões de qualidade por semana: TEMPO (limiar) + TIROS ou VO2MAX, bem espaçadas.
- Sessões de TEMPO sustentado (Z3-Z4) são prioritárias para elevar FTP.
- Inclua VO2MAX a cada 2 semanas para elevar o teto aeróbico.
- Dias de recuperação em Z1/Z2 puro — o atleta deve chegar DESCANSADO nas sessões duras.
- Reduza Z2_LONGO se necessário para não comprometer qualidade das sessões duras.""",

    "base_aerobica": """OBJETIVO — CONSTRUIR BASE AERÓBICA:
- Maximizar volume em Z2 (FC abaixo do limiar de lactato). Sem sessões VO2MAX ou TIROS.
- Apenas Z2_LONGO, RECUPERACAO e TEMPO ocasional (1x semana no máximo).
- O longão de fim de semana é o treino central da semana — preservar sempre.
- Progressão de volume gradual (+5-10% por semana). Priorize consistência sobre intensidade.""",

    "manter_performance": """OBJETIVO — MANTER PERFORMANCE:
- Equilíbrio: 1 sessão dura (VO2MAX ou TIROS) + 2-3 Z2 + longão.
- Não reduza volume bruscamente nem aumente carga: mantenha o padrão das semanas anteriores.
- Foque em consistência — complete os treinos planejados sem sobrecarga.""",

    "emagrecimento": """OBJETIVO — EMAGRECIMENTO:
- Priorize volume de Z2 (alto gasto calórico, baixo cortisol, preserva músculo).
- Máximo 1 sessão dura por semana (VO2MAX ou TIROS) para manter estímulo metabólico.
- Longões de fim de semana são ESSENCIAIS: maior queima de gordura em Z2 prolongado.
- Evite 2 dias duros consecutivos — má recuperação sabota a perda de peso.
- Prefira Z2_LONGO e RECUPERACAO nos dias úteis.""",
}


def _instrucoes_objetivo(objetivo: str) -> str:
    return _INSTRUCOES_OBJETIVO.get(objetivo) or _INSTRUCOES_OBJETIVO["performance_mtb"]


def _proxima_semana(semana_atual: str) -> str:
    d = datetime.strptime(semana_atual, "%Y-%m-%d").date()
    return (d + timedelta(days=7)).isoformat()


def _shift_data(data_iso: str, delta_dias: int) -> str:
    d = datetime.strptime(data_iso, "%Y-%m-%d").date()
    return (d + timedelta(days=delta_dias)).isoformat()


# ── Regras de agenda (configuráveis por usuário) ──────────────────────────────
_MAX_MIN_DIA_UTIL = 120   # seg–sex: nenhum treino acima de 2h
_LONGAO_MIN = 180         # longão do fim de semana: 3h (Z2 / "for fun")
_LONGAO_DESC = "Longão for fun (~3h) — base aeróbica Z2, ritmo livre/conversacional. Foco em volume e economia de pedalada."

# Dias de treino padrão (Marciano: seg–sáb = 0..5)
_DIAS_TREINO_PADRAO = [0, 1, 2, 3, 4, 5]

# Regras de treino por fase de periodização (injetadas no prompt quando há prova).
_REGRAS_FASE = {
    "base": (
        "REGRAS DA FASE (BASE): priorize volume aeróbico e Z2; inclua FORCA; "
        "pouca alta intensidade (no máximo 1 dia mais forte). Construa base."
    ),
    "construcao": (
        "REGRAS DA FASE (CONSTRUÇÃO): introduza intensidade específica da prova "
        "(TIROS/VO2MAX/TEMPO conforme o terreno) e suba o volume progressivamente. "
        "Até 2 dias duros bem espaçados."
    ),
    "pico": (
        "REGRAS DA FASE (PICO): intensidade alta e específica da prova; o volume "
        "começa a cair. Qualidade acima de quantidade; recuperação reforçada."
    ),
    "taper": (
        "REGRAS DA FASE (POLIMENTO/TAPER): REDUZA o volume ~40-50% mantendo apenas "
        "estímulos CURTOS de intensidade para manter a forma. Nada de treino longo "
        "ou desgastante. Descanso reforçado nos 2-3 dias antes da prova. Chegue "
        "descansado e afiado."
    ),
}


def _aplicar_regras_agenda(
    data_iso: str,
    tipo: str,
    duracao,
    descricao,
    cadencia,
    preferencias: dict | None = None,
    fase: str | None = None,
):
    """Aplica regras de agenda generalizadas por preferências do usuário.

    Regras:
    - Dias não listados em dias_treino → DESCANSO (sobrescreve qualquer tipo).
    - Seg–sex (wd ≤ 4): teto de 120 min quando for dia de treino.
    - Sábado (wd == 5): se estiver nos dias_treino, SEMPRE longão de 180 min.
    - Se sábado NÃO estiver nos dias_treino mas houver dia de fim de semana (sáb/dom)
      nos dias_treino, o primeiro desses dias recebe o longão; caso contrário não
      há longão forçado (bom senso: semanas sem treino de fim de semana não precisam).
    - Domingo (wd == 6): se estiver nos dias_treino e não for o "dia do longão",
      não é modificado (livre para descanso/recuperação pela IA).

    Retorna (tipo, duracao, descricao, cadencia) ajustados.
    """
    pref = preferencias or {}
    dias_treino: list[int] = pref.get("dias_treino") or _DIAS_TREINO_PADRAO

    try:
        wd = datetime.strptime(data_iso, "%Y-%m-%d").weekday()  # 0=seg ... 6=dom
    except (ValueError, TypeError):
        return tipo, duracao, descricao, cadencia

    # 1) Dia fora dos dias de treino → DESCANSO
    if wd not in dias_treino:
        return "DESCANSO", None, "", cadencia

    # 2) Determina qual dia é o "dia do longão" (fim de semana com treino)
    #    Prioridade: sábado (5) > domingo (6). Se nenhum, não força longão.
    dia_longao: int | None = None
    for candidato in (5, 6):
        if candidato in dias_treino:
            dia_longao = candidato
            break

    # 3) Dia do longão → longão garantido de 3h.
    #    Em semana de taper (prova chegando), o longão encolhe para não cansar.
    if wd == dia_longao:
        if fase == "taper":
            return ("Z2_LONGO", 90,
                    "Rodagem leve de taper (~1h30) — Z2 solto, pernas leves para a prova.",
                    (cadencia or "85-95"))
        return "Z2_LONGO", _LONGAO_MIN, _LONGAO_DESC, (cadencia or "85-95")

    # 4) Dias úteis (seg–sex, wd ≤ 4) → teto de 2h (60 min no taper)
    if wd <= 4 and tipo != "DESCANSO" and duracao:
        teto = 60 if fase == "taper" else _MAX_MIN_DIA_UTIL
        duracao = min(int(duracao), teto)

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

    # ── Dados do usuário (tolerante a ausências) ──────────────────────────────
    u = await get_por_id(user_id)
    u = u or {}
    nome_atleta: str = u.get("nome") or "Atleta"
    perfil: dict = u.get("perfil") or {}
    preferencias: dict = u.get("preferencias") or {}
    zonas_doc: dict = u.get("zonas") or {}

    idade: int = int(perfil.get("idade") or 34)
    peso: float = float(perfil.get("peso_kg") or 85)
    objetivo: str = preferencias.get("objetivo") or "performance"

    # FC máx e limiar: prioriza zonas_doc (configurado via tela/Garmin),
    # cai para perfil, depois para defaults razoáveis.
    fc_max: int = int(zonas_doc.get("fc_max") or perfil.get("fc_max") or 190)
    limiar: int | None = zonas_doc.get("limiar") or perfil.get("limiar_bpm") or None

    # Zonas de FC: monta texto das faixas
    zonas_lista: list[dict] = zonas_doc.get("zonas") or []
    if zonas_lista:
        zonas_txt = " | ".join(
            f"Z{z['zona']} {z['min']}-{z['max']}" for z in zonas_lista
        )
        # Texto simplificado para o prompt (estilo "Z1 <145 | Z2 146-158 ...")
        zonas_prompt = " | ".join(
            f"Z{z['zona']} {z['min']}-{z['max']}" for z in zonas_lista
        )
    else:
        zonas_prompt = "Z1 <145 | Z2 146-158 | Z3 159-165 | Z4 166-177 | Z5 >177"

    limiar_txt = f" | Limiar de lactato: {limiar} bpm" if limiar else ""

    # Dias de treino para o prompt
    dias_treino: list[int] = preferencias.get("dias_treino") or _DIAS_TREINO_PADRAO
    _NOMES_DIA = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
    dias_treino_nomes = ", ".join(_NOMES_DIA[d] for d in sorted(dias_treino))

    # Determina dia do longão para o prompt (sáb > dom, ou nenhum)
    dia_longao_nome: str | None = None
    for candidato in (5, 6):
        if candidato in dias_treino:
            dia_longao_nome = _NOMES_DIA[candidato]
            break

    # Restrições de agenda para o prompt
    dias_uteis_treino = [d for d in dias_treino if d <= 4]
    if dias_uteis_treino:
        restricao_util = (
            f"- {', '.join(_NOMES_DIA[d].capitalize() for d in sorted(dias_uteis_treino))}: "
            f"NENHUM treino acima de 120 min (2h). Sessões de qualidade cabem em 2h."
        )
    else:
        restricao_util = "- Sem treinos em dias úteis configurados."

    if dia_longao_nome:
        restricao_fds = (
            f"- {dia_longao_nome.capitalize()}: SEMPRE um longão de 180 min (3h), "
            f"Z2_LONGO (\"for fun\", ritmo livre/base aeróbica). É o maior treino da semana."
        )
    else:
        restricao_fds = "- Sem longão fixo de fim de semana (sem treino em sáb/dom)."

    resumos = "\n".join(_resumo_treino(t) for t in treinos if t.get("tipo") != "DESCANSO")
    if not resumos:
        resumos = "  (nenhum treino com dados registrados)"

    # ── Próxima prova: periodização orientada ao objetivo ─────────────────────
    from app.services.prova_service import (
        proxima_prova, semanas_ate, fase_periodizacao, FASE_LABEL,
    )
    bloco_prova = ""
    fase_prova: str | None = None
    prova = await proxima_prova(user_id, ref=proxima)
    if prova:
        sem_rest = semanas_ate(prova["data"], ref=proxima)
        fase_prova = fase_periodizacao(sem_rest)
        det = []
        if prova.get("distancia_km"):
            det.append(f"{prova['distancia_km']} km")
        if prova.get("altimetria_m"):
            det.append(f"{prova['altimetria_m']} m de altimetria")
        if prova.get("terreno"):
            det.append(f"terreno {prova['terreno']}")
        if prova.get("prioridade"):
            det.append(f"prioridade {prova['prioridade']}")
        det_txt = (" — " + ", ".join(det)) if det else ""
        meta_txt = f"\nMeta do atleta: {prova['meta']}" if prova.get("meta") else ""
        bloco_prova = f"""
PRÓXIMA PROVA-ALVO: {prova['nome']} em {prova['data']} ({sem_rest} semana(s) restante(s)){det_txt}.{meta_txt}
FASE DE PERIODIZAÇÃO: {FASE_LABEL.get(fase_prova, fase_prova)}.
{_REGRAS_FASE.get(fase_prova, "")}
Direcione a semana para essa fase e para as exigências da prova (terreno/altimetria).
"""

    prompt = f"""Você é um coach de ciclismo MTB especializado em periodização progressiva.

ATLETA: {nome_atleta}, {idade} anos, {peso:.0f} kg, objetivo: {objetivo}.
FCMÁX: {fc_max} bpm{limiar_txt}
ZONAS GARMIN: {zonas_prompt}
DIAS DE TREINO: {dias_treino_nomes}
{bloco_prova}
SEMANA ATUAL ({semana_atual}):
{resumos}

DISTRIBUIÇÃO ATUAL DOS TREINOS:
{chr(10).join(f"  {t['data']} → {t.get('tipo','DESCANSO')}" for t in treinos)}

RESTRIÇÕES DE AGENDA (OBRIGATÓRIAS):
{restricao_util}
{restricao_fds}
- Dias SEM treino: DESCANSO obrigatório — não gere treino nesses dias.

{_instrucoes_objetivo(objetivo)}

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
        data = _fallback(treinos, proxima, preferencias)

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
        # regras de agenda (dias de treino, teto de 2h em dia útil, longão no fim de semana)
        tipo, duracao, descricao, cadencia = _aplicar_regras_agenda(
            t.get("data", ""), tipo, duracao, descricao, cadencia, preferencias, fase_prova)
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
        "fase":           fase_prova,
        "treinos":        treinos_out,
    }


def _fallback(treinos_atuais: list, proxima: str, preferencias: dict | None = None) -> dict:
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
        # regras de agenda (dias de treino, teto de 2h em dia útil, longão no fim de semana)
        tipo, dur, descricao, cadencia = _aplicar_regras_agenda(
            data_nova, tipo, dur, descricao, cadencia, preferencias)
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


# ─── Primeira semana (cold start, sem histórico nem Garmin) ───────────────────

# Sequência base de sessões para a 1ª semana de um atleta SEM histórico.
# Pensada para iniciante: volume modesto, muita base aeróbica (Z2) e
# recuperação, no máximo 1 dia de qualidade por objetivo. Os dias úteis recebem
# essa sequência em ordem; o dia de fim de semana (sáb>dom) vira um longão leve.
_PRIMEIRA_SEMANA_SEQ = {
    "performance_mtb":    ["RECUPERACAO", "TEMPO", "RECUPERACAO", "VO2MAX", "RECUPERACAO"],
    "aumentar_potencia":  ["RECUPERACAO", "TEMPO", "RECUPERACAO", "TIROS", "RECUPERACAO"],
    "base_aerobica":      ["Z2_LONGO", "RECUPERACAO", "Z2_LONGO", "RECUPERACAO", "Z2_LONGO"],
    "manter_performance": ["RECUPERACAO", "TEMPO", "RECUPERACAO", "FORCA", "RECUPERACAO"],
    "emagrecimento":      ["Z2_LONGO", "RECUPERACAO", "Z2_LONGO", "TEMPO", "RECUPERACAO"],
}

# Durações gentis para a 1ª semana (min). Mais curtas que os defaults: o novato
# está começando, então não queremos sobrecarregar logo de cara.
_PRIMEIRA_SEMANA_DUR = {
    "RECUPERACAO": 45,
    "Z2_LONGO":    75,
    "TEMPO":       55,
    "FORCA":       50,
    "TIROS":       50,
    "VO2MAX":      50,
}
_PRIMEIRA_SEMANA_LONGAO_MIN = 90   # longão leve de fim de semana p/ iniciante


def _dia_treino(data_iso: str, tipo: str, duracao=None, descricao="", cadencia=None) -> dict:
    return {
        "data": data_iso,
        "tipo": tipo,
        "duracao_min": duracao if tipo != "DESCANSO" else None,
        "descricao": descricao,
        "cadencia_rpm": cadencia,
    }


def _montar_primeira_semana_template(semana_inicio: str, objetivo: str,
                                     dias_treino: list[int]) -> list[dict]:
    """Monta deterministicamente a 1ª semana a partir do perfil. Sempre válida.

    - Dias fora de dias_treino → DESCANSO.
    - Dia de fim de semana (sáb>dom, se houver treino) → longão leve Z2.
    - Demais dias de treino → sequência base do objetivo, em ordem.
    """
    seq = _PRIMEIRA_SEMANA_SEQ.get(objetivo) or _PRIMEIRA_SEMANA_SEQ["performance_mtb"]
    dias_treino = sorted(dias_treino or _DIAS_TREINO_PADRAO)

    # Define o dia do longão (fim de semana com treino): sábado tem prioridade.
    dia_longao = next((c for c in (5, 6) if c in dias_treino), None)

    treinos: list[dict] = []
    slot = 0
    for offset in range(7):
        data = _shift_data(semana_inicio, offset)
        wd = offset  # semana_inicio é segunda → offset == weekday (0=seg..6=dom)

        if wd not in dias_treino:
            treinos.append(_dia_treino(data, "DESCANSO"))
            continue

        if wd == dia_longao:
            treinos.append(_dia_treino(
                data, "Z2_LONGO", _PRIMEIRA_SEMANA_LONGAO_MIN,
                "Longão leve de base aeróbica (Z2). Ritmo de conversa, sem forçar — "
                "objetivo é tempo em movimento, não velocidade.", "85-95"))
            continue

        tipo = seq[slot % len(seq)]
        slot += 1
        treinos.append(_dia_treino(
            data, tipo, _PRIMEIRA_SEMANA_DUR.get(tipo, 50),
            _DESCRICAO_PADRAO.get(tipo, ""), "85-95"))

    return treinos


async def gerar_primeira_semana(user_id: str, semana_inicio: str) -> dict:
    """Gera a 1ª semana de treinos de um atleta SEM histórico nem Garmin.

    Backbone determinístico montado a partir do perfil (objetivo, dias de treino).
    Se a IA estiver disponível, refina as DESCRIÇÕES dos treinos (mantendo os
    tipos/durações conservadores do template). Nunca falha: se a IA der erro,
    devolve o template puro.
    """
    u = await get_por_id(user_id)
    u = u or {}
    nome_atleta = u.get("nome") or "Atleta"
    perfil = u.get("perfil") or {}
    pref = u.get("preferencias") or {}
    zonas_doc = u.get("zonas") or {}

    objetivo = pref.get("objetivo") or "performance_mtb"
    dias_treino = pref.get("dias_treino") or _DIAS_TREINO_PADRAO
    idade = int(perfil.get("idade") or 34)
    peso = float(perfil.get("peso_kg") or 80)
    fc_max = int(zonas_doc.get("fc_max") or perfil.get("fc_max") or 190)

    treinos = _montar_primeira_semana_template(semana_inicio, objetivo, dias_treino)

    # ── Refinamento opcional das descrições via IA (best-effort) ──────────────
    analise = (
        "Primeira semana montada a partir do seu perfil — volume leve para começar "
        "com segurança. Conforme você treinar e conectar o Garmin, os próximos planos "
        "ficam mais personalizados."
    )
    progressao = "Semana inicial conservadora: base aeróbica, recuperação e um toque de qualidade."

    resumo_dias = "\n".join(
        f"  {t['data']} ({_NOMES_DIA_CURTO(t['data'])}) → {t['tipo']}"
        f"{' ' + str(t['duracao_min']) + 'min' if t['duracao_min'] else ''}"
        for t in treinos
    )
    prompt = f"""Você é um coach de ciclismo MTB. Escreva descrições curtas e motivadoras
para a PRIMEIRA semana de treinos de um INICIANTE que não tem histórico.

ATLETA: {nome_atleta}, {idade} anos, {peso:.0f} kg, FCmáx {fc_max} bpm, objetivo: {objetivo}.

Mantenha EXATAMENTE os tipos e durações abaixo (não invente treinos novos, não mude dias):
{resumo_dias}

Para cada dia com treino, escreva uma descrição clara de 1-2 frases que um iniciante
entenda (o que fazer, intensidade em zona de FC, cadência). Para DESCANSO, deixe vazio.

Responda APENAS JSON válido, sem markdown:
{{
  "treinos": [
    {{"data": "YYYY-MM-DD", "descricao": "..."}}
  ]
}}"""

    try:
        response = _client.generate_content(prompt)
        raw = response.text.strip().replace("```json", "").replace("```", "").strip()
        data = json.loads(raw)
        desc_por_data = {
            t.get("data"): (t.get("descricao") or "").strip()
            for t in data.get("treinos", [])
        }
        for t in treinos:
            if t["tipo"] != "DESCANSO" and desc_por_data.get(t["data"]):
                t["descricao"] = desc_por_data[t["data"]]
    except Exception as e:
        logger.info("IA indisponível para refinar 1ª semana (%s) — usando template puro", e)

    return {
        "semana_inicio": semana_inicio,
        "analise_semana": analise,
        "progressao": progressao,
        "treinos": treinos,
    }


_NOMES_DIA_C = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]


def _NOMES_DIA_CURTO(data_iso: str) -> str:
    try:
        return _NOMES_DIA_C[datetime.strptime(data_iso, "%Y-%m-%d").weekday()]
    except (ValueError, TypeError):
        return "?"
