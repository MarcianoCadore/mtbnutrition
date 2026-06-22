"""Geração da próxima semana de treinos usando IA (Claude Opus)."""

import json
import logging
from datetime import datetime, timedelta

import anthropic

from config.settings import settings
from app.services.mongo_service import get_db
from app.services.user_service import get_por_id

logger = logging.getLogger(__name__)

_client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
_MODEL_PLANO = "claude-opus-4-8"  # melhor qualidade para geração de planos semanais

_TIPOS_VALIDOS = {"Z2_LONGO", "TIROS", "VO2MAX", "TEMPO", "FORCA", "ACADEMIA", "RECUPERACAO", "DESCANSO"}

_DURACAO_PADRAO = {
    "Z2_LONGO":    120,
    "TEMPO":        90,
    "FORCA":        90,
    "ACADEMIA":     65,
    "TIROS":        75,
    "VO2MAX":       75,
    "RECUPERACAO":  75,
    "DESCANSO":      0,
}

_DURACAO_MAXIMA = {
    "Z2_LONGO":    120,
    "TEMPO":       120,
    "FORCA":       120,
    "ACADEMIA":     90,
    "TIROS":        90,
    "VO2MAX":       90,
    "RECUPERACAO":  90,
}

_DESCRICAO_PADRAO = {
    "Z2_LONGO":    "Base aeróbica Z2. FC 146-158 bpm, cadência 85-95 rpm.",
    "TEMPO":       "3x10 min Z3 (159-165 bpm), recuperação Z2.",
    "FORCA":       "4x6 min Z3 cadência baixa (50-60 rpm), recuperação Z2.",
    "ACADEMIA":    "ACADEMIA — Força para MTB\n\nEXERCÍCIOS:\n1. Agachamento búlgaro — 4x8 cada perna (potência de subida)\n2. Stiff romeno com halteres — 3x10 (isquiotibiais e glúteos)\n3. Prancha abdominal — 4x45s\n4. Dead bug — 3x12 cada lado (estabilidade core no bike)\n5. Remada curvada — 3x10 (controle do guidão)\n6. Panturrilha em pé — 4x15\n\nOBSERVAÇÕES:\n- Descanso 90s entre séries\n- Foco em glúteos, core e estabilidade para MTB",
    "TIROS":       "8x30s Z5 (>177 bpm) com 3.5 min recuperação Z1.",
    "VO2MAX":      "4x4 min Z5 (>177 bpm) com 4 min recuperação Z2.",
    "RECUPERACAO": "Pedal leve Z1 (<145 bpm). Recuperação ativa.",
    "DESCANSO":    "",
}


_INSTRUCOES_OBJETIVO = {
    "performance_mtb": """OBJETIVO — PERFORMANCE MTB (modelo polarizado + progressão contínua):

ESTRUTURA SEMANAL:
- Exatamente 2 dias DUROS de bike, bem espaçados (nunca em dias consecutivos nem antes do longão).
- Combinações ideais de sessões duras: VO2MAX + TIROS, VO2MAX + TEMPO, ou TIROS + TEMPO.
- ACADEMIA conta como dia duro — nunca coloque ACADEMIA adjacente a VO2MAX, TIROS ou FORCA.
- Dias fáceis (Z2/RECUPERACAO) devem ser REALMENTE fáceis — FC abaixo de Z3. Sem "zona cinza".
- Longão de sábado é INEGOCIÁVEL: base aeróbica, ritmo conversacional.

PROGRESSÃO CONTÍNUA (use os dados da semana atual para decidir):
- Semana BEM executada (FC nos alvos, pontos fortes > pontos fracos): AUMENTAR carga (+5-10 min ou +1 repetição).
- Semana MEDIANA (alguns pontos fracos, FC um pouco alta): MANTER volume, ajustar intensidade.
- Semana DIFÍCIL (FC muito alta, muitos pontos fracos, incompleta): REDUZIR volume 10% e reforçar recuperação.
- A cada 4 semanas: semana de recuperação com volume -20-30%, sem VO2MAX.

DETALHAMENTO DAS SESSÕES DURAS (use dados reais das zonas do atleta na descrição):
- TIROS: progressão de 6→8→10→12 repetições de 30s Z5, com 3-4 min recuperação Z1. Cadência alta (95-110 rpm).
- VO2MAX: progressão de 4→5→6 blocos de 4-5 min Z5, recuperação igual ao bloco. Cadência 90-100 rpm.
- TEMPO: progressão de 2→3 blocos de 10-15 min Z3-Z4, recuperação 5 min Z2. Cadência 85-95 rpm.
- FORCA (bike): 4-6 blocos de 5-8 min cadência 50-60 rpm, marcha pesada, Z3. Fortalece musculatura de subida.

ESPECIFICIDADE MTB (MTB é diferente de estrada):
- Cadência variada e trabalho neuromuscular são essenciais para trilha.
- Inclua variações de cadência na descrição dos treinos (ex: sprints de cadência alta, subidas simuladas em cadência baixa).
- O longão Z2 deve incluir mudanças de ritmo ocasionais que simulem o terreno variado do MTB.""",

    "aumentar_potencia": """OBJETIVO — AUMENTAR POTÊNCIA / FTP:
- Priorize 2 sessões de qualidade por semana: TEMPO (limiar) + TIROS ou VO2MAX, bem espaçadas.
- Sessões de TEMPO sustentado (Z3-Z4) são prioritárias para elevar FTP — progressão: 2x10 → 2x15 → 3x10 → 3x15 min.
- Inclua VO2MAX a cada 2 semanas para elevar o teto aeróbico acima do limiar.
- Dias de recuperação em Z1/Z2 puro — o atleta deve chegar DESCANSADO nas sessões duras.
- Reduza Z2_LONGO se necessário para não comprometer qualidade das sessões de qualidade.""",

    "base_aerobica": """OBJETIVO — CONSTRUIR BASE AERÓBICA:
- Maximizar volume em Z2 (FC abaixo do limiar de lactato). Sem sessões VO2MAX ou TIROS ainda.
- Apenas Z2_LONGO, RECUPERACAO e TEMPO ocasional (1x semana no máximo, moderado).
- O longão de fim de semana é o treino central — preservar sempre, aumentar progressivamente.
- Progressão de volume gradual (+5-10% por semana). Priorize consistência sobre intensidade.
- A base sólida agora = mais potência quando intensidade for introduzida nas próximas fases.""",

    "manter_performance": """OBJETIVO — MANTER PERFORMANCE:
- Equilíbrio: 1 sessão dura (VO2MAX ou TIROS) + 2-3 Z2 + longão.
- Não reduza volume bruscamente nem aumente carga: mantenha o padrão das semanas anteriores.
- Foque em consistência — complete os treinos planejados sem sobrecarga.
- A cada 4-6 semanas: semana de recuperação para consolidar as adaptações.""",

    "emagrecimento": """OBJETIVO — EMAGRECIMENTO COM PRESERVAÇÃO DE PERFORMANCE:
- Priorize volume de Z2 (alto gasto calórico, baixo cortisol, preserva músculo e mitocôndrias).
- Máximo 1 sessão dura por semana (VO2MAX ou TIROS) para manter estímulo metabólico e massa magra.
- Longões de fim de semana são ESSENCIAIS: maior oxidação de gordura em Z2 prolongado (>90 min).
- Evite 2 dias duros consecutivos — má recuperação sabota a perda de peso e a performance.
- Prefira Z2_LONGO e RECUPERACAO nos dias úteis para manter déficit calórico sem sobrecarregar.""",
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
    if res.get("avg_power"):
        pot_txt = f"    Potência média: {res['avg_power']}W"
        if res.get("norm_power"):
            pot_txt += f" | NP: {res['norm_power']}W"
        linhas.append(pot_txt)
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

    # FTP e zonas de potência (para prescrições com watts)
    from app.services.config_service import get_zonas_potencia as _get_zp
    zp_doc = await _get_zp(user_id)
    ftp_user: int | None = zp_doc["ftp"] if zp_doc else None
    potencia_modo: str = (zp_doc or {}).get("potencia_modo", "indoor")
    zonas_pot_user: list[dict] = (zp_doc or {}).get("zonas", [])

    # Academia
    academia_cfg: dict = u.get("academia") or {}
    treina_academia: bool = bool(academia_cfg.get("treina"))
    academia_disp: dict = academia_cfg.get("disponibilidade") or {}
    academia_freq: int = int(academia_cfg.get("frequencia_semanal") or 0)

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

    # ── Bloco de academia para o prompt ──────────────────────────────────────
    _NOMES_PERIODO = {"manha": "manhã", "tarde": "tarde", "noite": "noite"}
    if treina_academia:
        if academia_disp:
            disp_txt = ", ".join(
                f"{_NOMES_DIA[int(d)]} ({_NOMES_PERIODO.get(p, p)})"
                for d, p in sorted(academia_disp.items(), key=lambda x: int(x[0]))
                if int(d) < 7
            )
            bloco_academia = f"ACADEMIA DO ATLETA: treina musculação. Dias/períodos disponíveis: {disp_txt}."
        else:
            bloco_academia = (
                "ACADEMIA DO ATLETA: treina musculação, mas não informou dias/períodos preferidos. "
                "A IA deve escolher automaticamente os melhores dias (adjacentes a treinos leves ou descanso)."
            )
    else:
        bloco_academia = (
            "ACADEMIA DO ATLETA: NÃO treina musculação. "
            "NÃO inclua sessões do tipo ACADEMIA. O campo academia deve ser null em todos os treinos."
        )

    # ── Próxima prova: periodização orientada ao objetivo ─────────────────────
    from app.services.prova_service import (
        proxima_prova, semanas_ate, fase_periodizacao, FASE_LABEL, listar_provas,
    )
    bloco_prova = ""
    fase_prova: str | None = None
    prova = await proxima_prova(user_id, ref=proxima)

    # Provas nas próximas 2 semanas (para taper/prioritization)
    proxima_mais2 = _shift_data(proxima, 14)
    todas_provas = await listar_provas(user_id)
    provas_2semanas = [
        p for p in todas_provas
        if proxima <= p["data"] <= proxima_mais2
    ]

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

    if provas_2semanas:
        linhas_p2 = []
        for p2 in provas_2semanas:
            sw = semanas_ate(p2["data"], ref=proxima)
            linhas_p2.append(f"  - {p2['nome']} em {p2['data']} ({sw} semana(s)) — prioridade {p2.get('prioridade','?')}")
        bloco_prova += f"""
⚠️ PROVAS NAS PRÓXIMAS 2 SEMANAS — planeje taper e recuperação:
{chr(10).join(linhas_p2)}
Se houver prova em menos de 7 dias: reduza volume, mantenha intensidade curta, priorize descanso.
"""

    if treina_academia:
        if academia_disp:
            disp_agenda = ", ".join(
                f"{_NOMES_DIA[int(d)]} ({_NOMES_PERIODO.get(p, p)})"
                for d, p in sorted(academia_disp.items(), key=lambda x: int(x[0]))
                if int(d) < 7
            )
            _intro_academia = (
                f"O atleta TREINA NA ACADEMIA. Dias/períodos disponíveis: {disp_agenda}.\n"
                "PRIORIDADE: agende sessões de ACADEMIA nesses dias/períodos.\n"
                "REGRA: dia de academia = tipo ACADEMIA EXCLUSIVAMENTE. Não coloque bike + academia no mesmo dia. "
                "O atleta vai à academia, não pedala naquele dia."
            )
        else:
            _intro_academia = (
                "O atleta TREINA NA ACADEMIA mas não informou dias preferidos.\n"
                "Escolha automaticamente os melhores dias: substitua DESCANSO por ACADEMIA nesses dias. "
                "NUNCA coloque academia em um dia que já tem bike — são atividades exclusivas. "
                "Nunca adjacente a VO2MAX ou TIROS."
            )
        _bloco_academia_prompt = f"""ACADEMIA (musculação no ginásio — tipo "ACADEMIA"):
{_intro_academia}

OBJETIVO DOS EXERCÍCIOS: aumentar DIRETAMENTE a performance na bike MTB.
  → Glúteos e isquiotibiais: potência nas pedaladas e subidas (agachamento búlgaro, stiff, hip thrust)
  → Core: estabilidade no bike, absorção de impacto em trilha (prancha, dead bug, pallof press, bird dog)
  → Quadríceps: força de saída e sprint (leg press, afundo, agachamento goblet)
  → Membros superiores/escapular: controle do guidão em técnico (remada, supino neutro, desenvolvimento)
  → Mobilidade de quadril e mobilidade torácica: manutenção da postura no bike

QUANTIDADE DE ACADEMIA POR SEMANA:{f" O ATLETA QUER EXATAMENTE {academia_freq} SESSÃO(ÕES) — respeite esse número." if academia_freq > 0 else " decisão sua (0, 1 ou 2). Analise a semana e decida:"}
A academia é um COMPLEMENTO ao bike. {"" if academia_freq > 0 else "Decida quantas sessões incluir (0, 1 ou no máximo 2):"}
{"" if academia_freq > 0 else "QUANDO INCLUIR 2 sessões: atleta completou bem os treinos; fase BASE/CONSTRUÇÃO com dias ociosos; análise apontou fraqueza de core/postura."}
{"" if academia_freq > 0 else "QUANDO INCLUIR 1 sessão: volume moderado de bike e há um dia com espaço; fase PICO: só 1 sessão leve de core."}
{"" if academia_freq > 0 else "QUANDO NÃO INCLUIR (0): semana sobrecarregada (VO2MAX+TIROS+longão+FORCA); fase TAPER; atleta com fadiga generalizada."}

⛔ REGRAS INVIOLÁVEIS — leia antes de posicionar qualquer sessão de academia:
1. NUNCA coloque ACADEMIA no dia ANTERIOR ou POSTERIOR a VO2MAX ou TIROS. Verifique os dois lados.
2. NUNCA crie 3 dias consecutivos duros (VO2MAX, TIROS, FORCA, ACADEMIA, Z2_LONGO ≥180min). Sempre intercale com RECUPERACAO ou DESCANSO.
3. ACADEMIA é dia exclusivo de musculação — tipo = "ACADEMIA", sem bike nesse dia. NÃO use o campo "academia" dentro de outro tipo de treino.

COMO ESCOLHER O FOCO DO TREINO DE ACADEMIA:
  * Dia anterior ou posterior DURO (VO2MAX, TIROS, FORCA, Z2_LONGO ≥180 min): PARTE SUPERIOR + CORE puro. PROIBIDO perna pesada.
  * Dia anterior e posterior LEVES (RECUPERACAO, DESCANSO): MEMBROS INFERIORES + CORE (agachamento búlgaro, hip thrust, stiff).

Formato OBRIGATÓRIO da "descricao" para ACADEMIA:
  "ACADEMIA — Força MTB (foco: [glúteos+core / pernas+core / superior+core])\\n\\nPOR QUE HOJE: [1-2 frases explicando a escolha]\\n\\nEXERCÍCIOS:\\n1. [exercício] — [séries]x[reps/tempo] ([benefício para MTB])\\n2. ...\\n\\nOBSERVAÇÕES:\\n- Descanso 90s entre séries\\n- [dica prática de MTB]"
"""
    else:
        _bloco_academia_prompt = (
            'ACADEMIA: O atleta NÃO treina musculação. '
            'NÃO inclua sessões do tipo ACADEMIA. O campo "academia" deve ser null em todos os treinos.'
        )

    # Bloco de potência para o prompt
    if ftp_user and zonas_pot_user:
        zonas_pot_txt = " | ".join(
            f"Z{z['zona']}({z['nome']}) {z['min']}-{z['max'] if z['max']<9000 else '∞'}W"
            for z in zonas_pot_user
        )
        _uso_pot = {
            "indoor": "Usa potência apenas no rolo (VO2MAX, TIROS, TEMPO, FORCA). Z2_LONGO e RECUPERACAO são feitos na rua sem medidor.",
            "sempre": "Tem medidor de potência em todas as bikes — SEMPRE prescreva watts.",
            "nunca":  "Sem medidor de potência — prescreva APENAS por FC.",
        }.get(potencia_modo, "")
        bloco_potencia = f"FTP: {ftp_user}W\nZONAS DE POTÊNCIA: {zonas_pot_txt}\n{_uso_pot}"
    else:
        bloco_potencia = "FTP não configurado — prescreva intensidade apenas por FC."

    prompt = f"""Você é um coach de ciclismo MTB de alto nível, especializado em periodização progressiva e desenvolvimento de performance na bike.

ATLETA: {nome_atleta}, {idade} anos, {peso:.0f} kg, objetivo: {objetivo}.
FCMÁX: {fc_max} bpm{limiar_txt}
ZONAS GARMIN: {zonas_prompt}
{bloco_potencia}
DIAS DE TREINO: {dias_treino_nomes}
{bloco_academia}
{bloco_prova}
═══════════════════════════════════════════
ANÁLISE DA SEMANA ATUAL ({semana_atual}):
{resumos}

DISTRIBUIÇÃO ATUAL DOS TREINOS:
{chr(10).join(f"  {t['data']} → {t.get('tipo','DESCANSO')}{(' | ' + str(t.get('duracao_min')) + 'min') if t.get('duracao_min') else ''}" for t in treinos)}

COMO USAR ESSES DADOS PARA DECIDIR A PRÓXIMA SEMANA:
- FC média ABAIXO do alvo da zona → treino ficou fácil → AUMENTAR carga (mais tempo, mais repetições ou zona mais alta).
- FC média DENTRO do alvo → execução ideal → MANTER estrutura e progredir levemente (+5-10 min ou +1 rep).
- FC média ACIMA do alvo → treino foi duro → MANTER ou REDUZIR volume antes de progredir.
- Pontos fracos recorrentes → escolher tipos de treino que ataquem diretamente essa fraqueza.
- Treino incompleto ou não realizado → NÃO progredir esse tipo de sessão; manter ou reduzir.
═══════════════════════════════════════════

RESTRIÇÕES DE AGENDA (OBRIGATÓRIAS):
{restricao_util}
{restricao_fds}
- Dias SEM treino: DESCANSO obrigatório — não gere treino nesses dias.

{_instrucoes_objetivo(objetivo)}

TIPOS DE TREINO NA BIKE — PRESCRIÇÃO DETALHADA (use nas descrições com as zonas reais do atleta):

- Z2_LONGO: Base aeróbica. FC em {zonas_prompt.split('|')[1].strip() if '|' in zonas_prompt else 'Z2'}.
  Descrição deve incluir: duração total, FC alvo, cadência (85-95 rpm), observação de ritmo conversacional.
  Duração típica em dia útil: 90-120 min. Use os dados da semana anterior para decidir.
  Ex: "105 min base aeróbica Z2 ({zonas_prompt.split('|')[1].strip() if '|' in zonas_prompt else 'Z2 bpm'}). Cadência 85-95 rpm, ritmo conversacional. Mantenha FC estável — desacelere nas subidas."

- RECUPERACAO: Pedal muito leve Z1. FC mínima possível. Ativa circulação, não gera fadiga.
  Duração: proporcional à carga da semana anterior — se o atleta fez longões de 2h+, use 75-90 min; semanas leves use 45-60 min. NÃO use valor fixo.
  Ex: "75 min recuperação ativa Z1 (<{zonas_prompt.split('|')[0].replace('Z1','').strip() if '|' in zonas_prompt else '145'} bpm). Sem esforço — só mover as pernas."

- TEMPO (limiar): Treino de limiar para elevar FTP. FC em Z3-Z4.
  Descrição deve incluir: aquecimento, blocos (N×X min), FC alvo por bloco, recuperação entre blocos, volta à calma.
  Duração típica: 90-105 min (aquecimento 15min + blocos + recuperações + volta à calma 10min).
  Ex: "15 min aquecimento Z1-Z2. 3×15 min Z3-Z4 ({zonas_prompt.split('|')[2].strip() if len(zonas_prompt.split('|'))>2 else '159-177 bpm'}), recuperação 5 min Z2 entre blocos. Cadência 88-95 rpm. 10 min volta à calma Z1."

- TIROS (neuromuscular/sprint): Alta intensidade Z5. Desenvolve potência e capacidade anaeróbica.
  Descrição deve incluir: aquecimento, número de repetições, duração do esforço, FC alvo, recuperação, cadência alta.
  Duração típica: 75-90 min (aquecimento longo + tiros + recuperações + volta à calma).
  Ex: "20 min aquecimento progressivo. 10×30s sprint máximo Z5 (>{fc_max - 13} bpm), cadência 100-115 rpm. Recuperação 3.5 min Z1 entre cada. 15 min volta à calma."

- VO2MAX: Blocos longos em Z5 para elevar VO2max e potência aeróbica máxima.
  Descrição deve incluir: aquecimento, número de blocos, duração do bloco, FC alvo, recuperação igual ao esforço, cadência.
  Duração típica: 75-90 min (aquecimento + blocos com recuperação igual + volta à calma).
  Ex: "15 min aquecimento progressivo até Z3. 5×4 min Z5 (>{fc_max - 13} bpm), cadência 90-100 rpm. Recuperação 4 min Z2 entre blocos. 15 min volta à calma Z1."

- FORCA (treino de força na BIKE — NÃO é academia):
  Cadência baixa (50-60 rpm), marcha pesada, FC em Z3. Simula subidas longas e fortalece musculatura de pedalada.
  Duração típica: 90-105 min.
  Ex: "15 min aquecimento. 6×8 min cadência 50-58 rpm marcha pesada Z3, subida ou resistência alta. Recuperação 3 min Z1 cadência livre. 10 min volta à calma."

{_bloco_academia_prompt}

{"POTÊNCIA (WATTS) NAS PRESCRIÇÕES:" + chr(10) + ("Inclua o alvo em watts NA DESCRIÇÃO de TODOS os treinos: ex. 'Z2 FC 146-158 bpm | 171-231W'." if potencia_modo == "sempre" else "Inclua o alvo em watts NA DESCRIÇÃO dos treinos de qualidade (VO2MAX, TIROS, TEMPO, FORCA): ex. '4×4 min Z5 >177 bpm | >327W'. Z2_LONGO e RECUPERACAO não têm potência (feitos na rua sem medidor).") if ftp_user else ""}

REGRAS DE PROGRESSÃO:
- Aumentar volume (+5-10% em duracao_min) quando a semana foi bem executada, respeitando o teto de 120 min em dias úteis.
- Manter ou reduzir se houve dificuldades (pontos fracos > pontos fortes).
- DESCANSO permanece DESCANSO nos mesmos dias.
- Para TIROS: aumentar número de repetições (8→10→12) antes de aumentar duração.
- Para VO2MAX: aumentar reps (4→5) antes de aumentar a duração dos blocos.

Responda APENAS em JSON válido, sem markdown, sem texto extra.
IMPORTANTE: gere os "treinos" PRIMEIRO — depois escreva "analise_semana" e "progressao" refletindo o que foi realmente gerado:
{{
  "treinos": [
    {{
      "data": "YYYY-MM-DD",
      "tipo": "TIPO",
      "duracao_min": 90,
      "descricao": "Prescrição COMPLETA do treino: aquecimento + estrutura principal (séries×tempo, FC alvo em bpm, cadência) + volta à calma. Para ACADEMIA: lista completa de exercícios com séries×reps.",
      "cadencia_rpm": "85-95",
      "academia": null
    }}
  ],
  "analise_semana": "Avaliação objetiva da semana atual: o que foi bem, o que foi fraco, como a FC se comportou vs. o alvo. 2-3 frases diretas.",
  "progressao": "Resumo do que foi gerado: tipos de treino incluídos, decisão de volume/intensidade e POR QUÊ — baseado nos dados da semana. NÃO mencione treinos que não foram incluídos nos treinos acima."
}}

REGRAS DO JSON:
- "cadencia_rpm" deve ser null para dias ACADEMIA puro (é ginásio, não bike).
- ACADEMIA é sempre tipo exclusivo — nunca use o campo "academia" como sub-objeto dentro de outro tipo. Um dia = uma atividade.
- Exatamente 7 entradas em "treinos" (uma por dia: {proxima} a {_shift_data(proxima, 6)}).
- Descrições de treinos de bike devem sempre incluir FC alvo em bpm (usando as zonas reais do atleta).
- O campo "progressao" deve descrever APENAS o que está nos treinos gerados acima — não mencione academia se nenhum dia tiver tipo ACADEMIA.
"""

    try:
        response = await _client.messages.create(
            model=_MODEL_PLANO,
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip().replace("```json", "").replace("```", "").strip()
        data = json.loads(raw)
    except Exception as e:
        logger.warning("Claude falhou para gerar próxima semana: %s — usando fallback", e)
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
        # ACADEMIA puro não tem cadência (é gym, não bike)
        cadencia = None if tipo == "ACADEMIA" else t.get("cadencia_rpm")
        # regras de agenda (dias de treino, teto de 2h em dia útil, longão no fim de semana)
        tipo, duracao, descricao, cadencia = _aplicar_regras_agenda(
            t.get("data", ""), tipo, duracao, descricao, cadencia, preferencias, fase_prova)
        treino_out: dict = {
            "data":        t.get("data", ""),
            "tipo":        tipo,
            "duracao_min": duracao if tipo != "DESCANSO" else None,
            "descricao":   descricao,
            "cadencia_rpm": cadencia,
        }
        # sub-objeto academia (bike + gym no mesmo dia)
        academia_sub = t.get("academia")
        if academia_sub and isinstance(academia_sub, dict) and academia_sub.get("descricao"):
            treino_out["academia"] = {
                "duracao_min": int(academia_sub.get("duracao_min") or 60),
                "descricao": academia_sub["descricao"],
            }
        treinos_out.append(treino_out)

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
    """Gera a semana de treinos para um atleta.

    Se houver histórico (semana anterior com dados), delega para gerar_proxima_semana
    usando a semana mais recente — assim o plano reflete a progressão real do atleta.

    Sem histórico, usa um template conservador adequado para iniciantes.
    """
    db = get_db()
    semana_anterior = await db.semanas.find_one(
        {"user_id": user_id, "semana_inicio": {"$lt": semana_inicio}},
        sort=[("semana_inicio", -1)],
    )
    if semana_anterior:
        return await gerar_proxima_semana(user_id, semana_anterior["semana_inicio"])

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
        response = await _client.messages.create(
            model=_MODEL_PLANO,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip().replace("```json", "").replace("```", "").strip()
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
