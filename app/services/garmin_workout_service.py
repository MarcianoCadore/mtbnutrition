"""Builders de CyclingWorkout para o Garmin Connect.

Os alvos são montados por NÚMERO de zona (Z1 aquecimento, Z2 fácil, Z3 aeróbico,
Z4 limiar, Z5 máximo) e convertidos para as faixas reais de bpm/watts de CADA
atleta em tempo de envio (_aplicar_bpm / _aplicar_watts, a partir das zonas
configuradas pelo usuário). Nenhuma faixa fixa é embutida aqui — cada atleta tem
suas próprias frequências e potências.
"""

import asyncio
import logging
from datetime import datetime

from app.services.prescricao_service import parse_prescricao
from garminconnect.workout import (
    CyclingWorkout,
    WorkoutSegment,
    SportType,
    TargetType,
    create_warmup_step,
    create_interval_step,
    create_recovery_step,
    create_cooldown_step,
    create_repeat_group,
)

logger = logging.getLogger(__name__)

# Tipos de treino feitos no rolo (indoor) — recebem alvo de watts quando modo="indoor"
_TIPOS_INDOOR = {"VO2MAX", "TIROS", "TEMPO", "FORCA", "TESTE_FTP"}

# ── helpers ──────────────────────────────────────────────────────────────────

_CYCLING_SPORT = {
    "sportTypeId": SportType.CYCLING,
    "sportTypeKey": "cycling",
    "displayOrder": 2,
}


def _hz(zone: int) -> dict:
    """Alvo de zona de FC (1-5)."""
    return {
        "workoutTargetTypeId": TargetType.HEART_RATE,
        "workoutTargetTypeKey": "heart.rate.zone",
        "displayOrder": 1,
        "targetValue": zone,
    }


def _pw(zona_fc: int) -> int:
    """Mapeia zona de FC (1-5) para zona de potência Coggan equivalente (1-7)."""
    return {1: 1, 2: 2, 3: 3, 4: 4, 5: 5}.get(zona_fc, zona_fc)


def _seg(steps: list) -> WorkoutSegment:
    return WorkoutSegment(segmentOrder=1, sportType=_CYCLING_SPORT, workoutSteps=steps)


# ── alvos: da zona (1-5) para as faixas reais do atleta ──────────────────────
#
# Os builders marcam cada step com o NÚMERO da zona (_hz). Aqui esse número vira
# a faixa de bpm ou de watts do atleta. O Garmin aceita um alvo PRIMÁRIO e um
# SECUNDÁRIO por step — com os dois preenchidos o relógio mostra watts e FC na
# mesma tela do treino, e o atleta segue a métrica que tiver no dia (medidor no
# rolo, cinta na trilha). Só o primário aciona o alerta de "fora do alvo".

# Campos do alvo secundário — separados porque `_sem_secundario` precisa removê-los
# se o Garmin recusar o upload (nem toda conta/firmware aceita alvo duplo).
_CAMPOS_SECUNDARIOS = (
    "secondaryTargetType",
    "secondaryTargetValueOne",
    "secondaryTargetValueTwo",
)


def _alvo_fc(rng: dict | None, zona: int) -> tuple[dict, float | None, float | None]:
    """Alvo de FC: faixa de bpm do atleta ou, sem faixa configurada, a zona do
    próprio dispositivo."""
    if not rng:
        return ({"workoutTargetTypeId": TargetType.HEART_RATE,
                 "workoutTargetTypeKey": "heart.rate.zone",
                 "displayOrder": 1,
                 "zoneNumber": zona}, None, None)
    return ({"workoutTargetTypeId": TargetType.HEART_RATE,
             "workoutTargetTypeKey": "heart.rate",
             "displayOrder": 1},
            float(rng["min"]), float(rng["max"]))


def _alvo_watts(rng: dict | None) -> tuple[dict, float, float] | None:
    """Alvo de potência em watts explícitos. None se a zona não tem faixa."""
    if not rng:
        return None
    # a Z7 é aberta no topo (max 9999) — vira "o dobro do piso" para o relógio
    teto = rng["max"] if rng["max"] < 9000 else rng["min"] * 2
    return ({"workoutTargetTypeId": TargetType.POWER,
             "workoutTargetTypeKey": "power",
             "displayOrder": 1},
            float(rng["min"]), float(teto))


def _aplicar_alvos(steps: list, *, zonas_bpm: dict | None = None,
                   zonas_watts: dict | None = None, primario: str = "fc") -> None:
    """Converte (in-place, recursivo) o número da zona de cada step nas faixas
    reais do atleta.

    `primario` ("fc" ou "watts") escolhe qual métrica vira o alvo principal do
    relógio. Se a OUTRA também tiver faixas, ela vai junto como alvo secundário —
    é o que faz o Garmin mostrar watts e FC na mesma tela.
    """
    for step in steps:
        filhos = getattr(step, "workoutSteps", None)
        if filhos:
            _aplicar_alvos(filhos, zonas_bpm=zonas_bpm, zonas_watts=zonas_watts,
                           primario=primario)
            continue
        tt = getattr(step, "targetType", None)
        if not tt or tt.get("workoutTargetTypeId") != TargetType.HEART_RATE:
            continue
        zona = tt.get("targetValue")
        if not zona:
            continue

        fc = _alvo_fc(zonas_bpm.get(zona) if zonas_bpm else None, zona)
        watts = _alvo_watts(zonas_watts.get(_pw(zona)) if zonas_watts else None)

        # sem FTP configurado não há alvo de watts: cai para FC seja qual for a preferência
        ordem = [watts, fc] if (primario == "watts" and watts) else [fc, watts]
        (step.targetType, step.targetValueOne, step.targetValueTwo) = ordem[0]

        for campo in _CAMPOS_SECUNDARIOS:
            if hasattr(step, campo):
                delattr(step, campo)
        secundario = ordem[1]
        # só vale como secundário o alvo com faixa numérica: "zona do dispositivo"
        # (heart.rate.zone) não tem valor para preencher o segundo campo do relógio
        if secundario and secundario[1] is not None:
            tipo, v1, v2 = secundario
            step.secondaryTargetType = {**tipo, "displayOrder": 4}
            step.secondaryTargetValueOne = v1
            step.secondaryTargetValueTwo = v2


def _sem_secundario(steps: list) -> None:
    """Remove os alvos secundários (recursivo). Rede de segurança: se o Garmin
    recusar o alvo duplo, o treino sobe com o alvo primário em vez de o atleta
    ficar sem treino no relógio."""
    for step in steps:
        filhos = getattr(step, "workoutSteps", None)
        if filhos:
            _sem_secundario(filhos)
            continue
        for campo in _CAMPOS_SECUNDARIOS:
            if hasattr(step, campo):
                delattr(step, campo)


def _tem_secundario(steps: list) -> bool:
    for step in steps:
        filhos = getattr(step, "workoutSteps", None)
        if filhos:
            if _tem_secundario(filhos):
                return True
        elif hasattr(step, "secondaryTargetType"):
            return True
    return False


# ── escala por duração ────────────────────────────────────────────────────────
#
# Todo builder DEVE devolver total == duracao_min * 60. O treino planejado vai pro
# Garmin com esse total em `estimatedDurationInSecs` e o pull seguinte
# (garmin_service.sync_treinos_planejados) lê esse campo de volta e regrava
# `duracao_min` no banco. Se o builder ignorar a duração pedida, o round-trip
# reescreve o plano com a duração do template — o atleta pede 110 min e o app
# "volta sozinho" pros 70 min do molde.

# Pontas nunca ficam abaixo disto: aquecer/desaquecer menos que 5 min não cumpre
# o papel. Só duração irreal (< ~20 min de intervalado) estoura o tempo pedido.
_MIN_AQUECIMENTO_S = 300
_MIN_VOLTA_CALMA_S = 300
# Sobra menor que isto não vira bloco próprio (vira aquecimento) — evita um step
# solto de 40 segundos no relógio.
_MIN_BLOCO_S = 300

# Sobra menor que isto some nas pontas em vez de virar rodagem Z2. Menos que ~20
# min não é uma parte da sessão, é o desencontro entre a duração planejada para o
# dia e a soma da prescrição — e como bloco separado ele aparece no gráfico como
# uma série a mais, contradizendo o "3×15 min" que o atleta acabou de ler.
_SOBRA_VIRA_RODAGEM_S = 20 * 60


def _encolher_pontas(total_s: int, aquecimento_s: int, volta_calma_s: int,
                     miolo_s: int) -> tuple[int, int]:
    """Corta aquecimento/volta à calma (até os mínimos) para caber `miolo_s` no tempo
    total. Corta proporcional à folga de cada ponta."""
    falta = miolo_s - (total_s - aquecimento_s - volta_calma_s)
    folga_aq = max(0, aquecimento_s - _MIN_AQUECIMENTO_S)
    folga_vc = max(0, volta_calma_s - _MIN_VOLTA_CALMA_S)
    if falta <= 0 or not (folga_aq + folga_vc):
        return aquecimento_s, volta_calma_s
    corte = min(falta, folga_aq + folga_vc)
    corte_aq = min(folga_aq, round(corte * folga_aq / (folga_aq + folga_vc)))
    corte_vc = min(folga_vc, corte - corte_aq)
    corte_aq = min(folga_aq, corte - corte_vc)   # devolve à outra ponta o que sobrou
    return aquecimento_s - corte_aq, volta_calma_s - corte_vc


def _total_s(duracao_min: int | None) -> int:
    return max(int(duracao_min or 0), 1) * 60


def _continuo(duracao_min: int | None, *, zona_miolo: int, zona_pontas: int,
              aquecimento_s: int, volta_calma_s: int) -> tuple[list, int]:
    """Aquecimento + bloco único + volta à calma. O bloco absorve a duração pedida."""
    total = _total_s(duracao_min)
    aq, vc = _encolher_pontas(total, aquecimento_s, volta_calma_s, _MIN_BLOCO_S)
    miolo = max(_MIN_BLOCO_S, total - aq - vc)
    steps = [
        create_warmup_step(aq, step_order=1, target_type=_hz(zona_pontas)),
        create_interval_step(miolo, step_order=2, target_type=_hz(zona_miolo)),
        create_cooldown_step(vc, step_order=3, target_type=_hz(zona_pontas)),
    ]
    return steps, aq + miolo + vc


def _intervalado(duracao_min: int | None, *, intervalo_s: int, recuperacao_s: int,
                 zona_intervalo: int, zona_recuperacao: int, zona_pontas: int,
                 aquecimento_s: int, volta_calma_s: int,
                 series_max: int,
                 zona_aquecimento: int | None = None,
                 zona_volta_calma: int | None = None) -> tuple[list, int]:
    """Aquecimento + N séries + (rodagem Z2) + volta à calma.

    A duração pedida é preenchida somando séries — o bloco (esforço + recuperação)
    é a assinatura do tipo e não muda de tamanho. Acima de `series_max` a sessão
    ficaria desproporcional, então o tempo restante vira rodagem Z2 antes da volta
    à calma — mas só quando é tempo de pedal de verdade (`_SOBRA_VIRA_RODAGEM_S`);
    abaixo disso ele alonga as pontas, sem inventar um bloco no gráfico.

    `zona_aquecimento`/`zona_volta_calma` separam as pontas quando a prescrição do
    dia dá zonas diferentes para elas ("aquecimento Z1→Z2 ... volta à calma Z1");
    sem isso as duas seguem `zona_pontas`.
    """
    total = _total_s(duracao_min)
    bloco = intervalo_s + recuperacao_s
    aq, vc = _encolher_pontas(total, aquecimento_s, volta_calma_s, bloco)

    series = max(1, min(series_max, (total - aq - vc) // bloco))
    sobra = max(0, total - aq - vc - series * bloco)
    if sobra < _SOBRA_VIRA_RODAGEM_S:
        # Sobra pequena vai para as pontas, na proporção delas. É a diferença
        # entre a duração planejada para o dia e a soma da prescrição ("3×15 min
        # + pontas" = 90 min num dia de 100): virar um bloco no meio do desenho
        # faz o atleta contar uma série que ninguém prescreveu.
        extra_aq = round(sobra * aq / (aq + vc)) if (aq + vc) else sobra
        aq += extra_aq
        vc += sobra - extra_aq
        sobra = 0

    inner = [
        create_interval_step(intervalo_s, step_order=1, target_type=_hz(zona_intervalo)),
        create_recovery_step(recuperacao_s, step_order=2, target_type=_hz(zona_recuperacao)),
    ]
    steps = [
        create_warmup_step(aq, step_order=1, target_type=_hz(zona_aquecimento or zona_pontas)),
        create_repeat_group(series, inner, step_order=2),
    ]
    if sobra:
        steps.append(create_interval_step(sobra, step_order=3, target_type=_hz(2)))
    steps.append(create_cooldown_step(
        vc, step_order=len(steps) + 1, target_type=_hz(zona_volta_calma or zona_pontas)))
    return steps, aq + series * bloco + sobra + vc


# ── builders por TipoTreino ───────────────────────────────────────────────────

def _recuperacao(duracao_min: int = 55) -> tuple[list, int]:
    """Z1 contínuo — recuperação ativa."""
    return _continuo(duracao_min, zona_miolo=1, zona_pontas=1,
                     aquecimento_s=600, volta_calma_s=600)


def _z2_longo(duracao_min: int = 120) -> tuple[list, int]:
    """Z2 sustentado — base aeróbica."""
    return _continuo(duracao_min, zona_miolo=2, zona_pontas=1,
                     aquecimento_s=900, volta_calma_s=900)


# Moldes dos tipos intervalados. Valem quando a descrição do dia NÃO diz a série
# (ver _params_da_prescricao): o texto do treino manda, o molde só preenche o que
# ele não disser.
_MOLDES_INTERVALADO = {
    "TEMPO":  dict(intervalo_s=600, recuperacao_s=300, zona_intervalo=3,
                   zona_recuperacao=2, zona_pontas=2,
                   aquecimento_s=900, volta_calma_s=600, series_max=5),
    "FORCA":  dict(intervalo_s=360, recuperacao_s=240, zona_intervalo=3,
                   zona_recuperacao=2, zona_pontas=2,
                   aquecimento_s=900, volta_calma_s=600, series_max=6),
    "TIROS":  dict(intervalo_s=30, recuperacao_s=210, zona_intervalo=5,
                   zona_recuperacao=1, zona_pontas=2,
                   aquecimento_s=900, volta_calma_s=900, series_max=12),
    "VO2MAX": dict(intervalo_s=240, recuperacao_s=240, zona_intervalo=5,
                   zona_recuperacao=2, zona_pontas=2,
                   aquecimento_s=900, volta_calma_s=900, series_max=6),
}


def _tempo(duracao_min: int = 70) -> tuple[list, int]:
    """Blocos de 10 min Z3 com 5 min de recuperação Z2 — esforço de limiar."""
    return _intervalado(duracao_min, **_MOLDES_INTERVALADO["TEMPO"])


def _forca(duracao_min: int = 65) -> tuple[list, int]:
    """Blocos de 6 min Z3 em cadência baixa (50-60 rpm) com 4 min Z2 — força específica."""
    return _intervalado(duracao_min, **_MOLDES_INTERVALADO["FORCA"])


def _tiros(duracao_min: int = 62) -> tuple[list, int]:
    """Sprints de 30s Z5 com 3,5 min de recuperação Z1 — neuromuscular."""
    return _intervalado(duracao_min, **_MOLDES_INTERVALADO["TIROS"])


def _vo2max(duracao_min: int = 62) -> tuple[list, int]:
    """Blocos de 4 min Z5 com 4 min de recuperação Z2 — VO2max."""
    return _intervalado(duracao_min, **_MOLDES_INTERVALADO["VO2MAX"])


def _teste_ftp(duracao_min: int = 57) -> tuple[list, int]:
    """Protocolo completo de teste FTP de 20min.

    O protocolo (progressivo + acelerações + teste) é fixo — é o que dá o número.
    A duração pedida só alonga/encurta as pontas e, se sobrar, uma rodagem Z2 depois
    do teste.
    """
    # Aquecimento Z1 — 10min
    # Progressivo Z3 — 5min
    # 3x (30seg Z5 + 1min Z1 recuperação)
    # Pré-teste Z1 — 2min suave
    # TESTE FTP Z4 — 20min potência máxima sustentável
    # (rodagem Z2 — só se a duração pedida pedir mais tempo)
    # Desaquecimento Z1 — 15min
    protocolo_s = 300 + 3 * (30 + 60) + 120 + 1200
    total = _total_s(duracao_min)
    aq, vc = _encolher_pontas(total, 600, 900, protocolo_s)
    sobra = max(0, total - aq - vc - protocolo_s)
    if sobra < _MIN_BLOCO_S:
        aq += sobra
        sobra = 0

    inner_acel = [
        create_interval_step(30, step_order=1, target_type=_hz(5)),
        create_recovery_step(60, step_order=2, target_type=_hz(1)),
    ]
    steps = [
        create_warmup_step(aq, step_order=1, target_type=_hz(1)),          # aquecimento Z1
        create_interval_step(300, step_order=2, target_type=_hz(3)),       # 5min Z3 progressivo
        create_repeat_group(3, inner_acel, step_order=3),                  # 3x aceleração
        create_interval_step(120, step_order=4, target_type=_hz(1)),       # 2min Z1 pré-teste
        create_interval_step(1200, step_order=5, target_type=_hz(4)),      # 20min TESTE FTP Z4
    ]
    if sobra:
        steps.append(create_interval_step(sobra, step_order=6, target_type=_hz(2)))
    steps.append(create_cooldown_step(vc, step_order=len(steps) + 1, target_type=_hz(1)))
    return steps, aq + protocolo_s + sobra + vc


_BUILDERS = {
    "RECUPERACAO": _recuperacao,
    "Z2_LONGO":    _z2_longo,
    "TEMPO":       _tempo,
    "FORCA":       _forca,
    "TIROS":       _tiros,
    "VO2MAX":      _vo2max,
    "TESTE_FTP":   _teste_ftp,
}

# NÃO embutir bpm/watts fixos aqui — cada atleta tem suas próprias zonas. As
# faixas reais são anexadas pela legenda (plano_semana_service._legenda_alvos) e
# o alvo enviado ao Garmin é calculado das zonas do atleta (_aplicar_bpm/_watts).
_DESCRICOES_PADRAO = {
    "RECUPERACAO": "Pedal leve em Z1. Recuperação ativa, esforço mínimo.",
    "Z2_LONGO":    "Base aeróbica em Z2. Cadência: 85-95 rpm. Esforço controlado.",
    "TEMPO":       "3x10 min em Z3 com 5 min de recuperação Z2. Esforço moderado-alto sustentado.",
    "FORCA":       "4x6 min em Z3 com cadência baixa (50-60 rpm). 4 min recuperação Z2 entre blocos.",
    "TIROS":       "8x30s em Z5 com 3.5 min recuperação Z1. Sprints máximos.",
    "VO2MAX":      "4x4 min em Z5 com 4 min recuperação Z2. Esforço VO2max sustentado.",
    "TESTE_FTP":   "TESTE FTP — 20min esforço máximo sustentável. Potência média × 0.95 = novo FTP. Não exploda no início!",
}


def _params_da_prescricao(tipo: str, descricao: str | None) -> dict | None:
    """Parâmetros de `_intervalado` lidos da DESCRIÇÃO do dia, completados pelo
    molde do tipo. None quando o texto não descreve uma série — aí vale o molde
    inteiro.

    É o que faz o gráfico do portal, o .zwo e o treino do relógio baterem com a
    prescrição que o atleta lê no card: "3×15 min" desenhava 5 blocos de 10 min
    porque só o molde do tipo era consultado.

    Só os tipos intervalados entram. Z2_LONGO/RECUPERACAO são contínuos, e o
    TESTE_FTP tem protocolo fixo (é ele que dá o número) cuja descrição ainda cita
    séries de aquecimento — "3×(30s Z5 + 1min Z1)" — que não são a sessão principal.
    """
    molde = _MOLDES_INTERVALADO.get(tipo)
    if not molde or not descricao:
        return None
    lido = parse_prescricao(descricao)
    if not lido:
        return None

    params = dict(molde)
    # A série descrita é a sessão: `series_max` vira o número de blocos do texto —
    # se não couberem na duração do dia, _intervalado corta pelo tempo disponível.
    params["series_max"] = lido["series"]
    params["intervalo_s"] = lido["esforco_s"]
    for no_texto, no_molde in (
        ("recuperacao_s",    "recuperacao_s"),
        ("zona_esforco",     "zona_intervalo"),
        ("zona_recuperacao", "zona_recuperacao"),
        ("aquecimento_s",    "aquecimento_s"),
        ("volta_calma_s",    "volta_calma_s"),
        ("zona_aquecimento", "zona_aquecimento"),
        ("zona_volta_calma", "zona_volta_calma"),
    ):
        if lido.get(no_texto) is not None:
            params[no_molde] = lido[no_texto]
    return params


def _estrutura(tipo: str, duracao_min: int, descricao: str | None = None) -> tuple[list, int] | None:
    """(steps, total_s) do treino: a série descrita para o dia quando o texto a
    traz, senão o molde do tipo. None se o tipo não tem estrutura."""
    params = _params_da_prescricao(tipo, descricao)
    if params:
        return _intervalado(duracao_min, **params)
    builder = _BUILDERS.get(tipo)
    return builder(duracao_min) if builder else None


def build_cycling_workout(
    tipo: str,
    duracao_min: int,
    nome: str,
    descricao: str | None = None,
    zonas_bpm: dict | None = None,
    zonas_watts: dict | None = None,
    primario: str = "fc",
) -> CyclingWorkout | None:
    """Monta um CyclingWorkout para o tipo e duração dados.

    'zonas_bpm' ({zona: {'min','max'}}) manda os alvos de FC como faixas de bpm
    explícitas em vez do número de zona do dispositivo. Passando também
    'zonas_watts', o step leva as DUAS métricas: `primario` ("fc"/"watts") define
    qual é o alvo principal e a outra vai como alvo secundário, visível na mesma
    tela do relógio.

    A estrutura sai da série descrita em `descricao` quando ela está lá — o
    relógio recebe o treino que o atleta lê no card, não o molde do tipo.
    """
    estrutura = _estrutura(tipo, duracao_min, descricao)
    if not estrutura:
        return None

    steps, total_s = estrutura
    if zonas_bpm or zonas_watts:
        _aplicar_alvos(steps, zonas_bpm=zonas_bpm, zonas_watts=zonas_watts,
                       primario=primario)
    return CyclingWorkout(
        workoutName=nome,
        estimatedDurationInSecs=total_s,
        description=descricao or _DESCRICOES_PADRAO.get(tipo, ""),
        workoutSegments=[_seg(steps)],
    )


def preview_estrutura(
    tipo: str,
    duracao_min: int,
    zonas_bpm: dict | None = None,
    zonas_watts: dict | None = None,
    descricao: str | None = None,
) -> dict | None:
    """Monta a lista plana de segmentos (aquecimento/intervalo/recuperação/volta à
    calma) do treino, para exibir como gráfico no portal — mesma fonte usada para
    montar o workout real enviado ao Garmin, então o gráfico nunca diverge do que o
    atleta recebe no relógio. Repeat groups são expandidos (cada repetição vira
    segmentos separados).

    `descricao` é a prescrição do dia: dela saem os blocos quando o texto os
    descreve ("3×15 min em Z3/Z4 com 5 min de recuperação"). Sem ela o desenho cai
    no molde do tipo — e foi assim que um treino de 3 blocos aparecia com 5.

    Se 'zonas_bpm'/'zonas_watts' forem passadas, cada segmento leva a faixa real
    (min/max) do atleta; caso contrário só a zona (1-5) é informada.
    """
    estrutura = _estrutura(tipo, duracao_min, descricao)
    if not estrutura:
        return None
    steps, total_s = estrutura

    def _faixa(zona: int) -> tuple[float | None, float | None, str | None]:
        if zonas_watts:
            rng = zonas_watts.get(_pw(zona))
            if rng:
                mx = rng["max"] if rng["max"] < 9000 else rng["min"] * 2
                return round(rng["min"]), round(mx), "W"
        if zonas_bpm:
            rng = zonas_bpm.get(zona)
            if rng:
                return rng["min"], rng["max"], "bpm"
        return None, None, None

    segmentos: list[dict] = []

    def _walk(lst: list) -> None:
        for step in lst:
            filhos = getattr(step, "workoutSteps", None)
            if filhos:
                iteracoes = getattr(step, "numberOfIterations", 1) or 1
                for _ in range(iteracoes):
                    _walk(filhos)
                continue
            fase = ((getattr(step, "stepType", None) or {}).get("stepTypeKey")) or "interval"
            zona = (getattr(step, "targetType", None) or {}).get("targetValue")
            duracao_s = int(getattr(step, "endConditionValue", 0) or 0)
            mn, mx, unidade = _faixa(zona) if zona else (None, None, None)
            segmentos.append({
                "fase": fase,
                "zona": zona,
                "duracao_s": duracao_s,
                "min": mn,
                "max": mx,
                "unidade": unidade,
            })

    _walk(steps)
    return {"segments": segmentos, "total_s": total_s}


async def upload_e_agendar(
    user_id: str,
    tipo: str,
    duracao_min: int,
    nome: str,
    data_iso: str,
    descricao: str | None = None,
    forcar_indoor: bool | None = None,
) -> str | None:
    """Faz upload do workout e agenda para a data. Retorna o garmin_workout_id.

    forcar_indoor:
      True  → força alvos em watts (usuário marcou "indoor" no dia)
      False → força alvos em FC (usuário marcou "outdoor" no dia)
      None  → usa a lógica do potencia_modo + tipo (comportamento padrão)

    No modo "ambos" o step leva watts E FC juntos: `forcar_indoor`/o tipo decidem
    qual é o alvo primário (o que dispara o alerta do relógio) e a outra métrica
    vai como secundária, para o atleta poder seguir a que tiver no dia.
    """
    from app.services.garmin_service import get_garmin_client
    from app.services.config_service import zonas_bpm_map, get_zonas_potencia

    zp = await get_zonas_potencia(user_id)
    modo = (zp or {}).get("potencia_modo", "indoor")
    usar_watts = False
    if zp:
        if forcar_indoor is not None:
            usar_watts = forcar_indoor
        else:
            usar_watts = (modo in ("sempre", "ambos")) or (
                modo in ("indoor", "ambos") and tipo in _TIPOS_INDOOR
            )

    zonas_bpm = await zonas_bpm_map(user_id)
    # Sem o gate por modo: o toggle indoor/outdoor do dia manda watts mesmo em
    # "nunca" — é uma escolha explícita do atleta para aquela sessão.
    zonas_w = ({z["zona"]: {"min": z["min"], "max": z["max"]} for z in zp["zonas"]}
               if zp else None)

    # "ambos" manda as duas métricas em todo step; nos outros modos só a escolhida
    # (senão quem pediu "só FC" receberia watts na tela do relógio).
    if modo == "ambos":
        bpm_arg, watts_arg = zonas_bpm, zonas_w
    elif usar_watts:
        bpm_arg, watts_arg = None, zonas_w
    else:
        bpm_arg, watts_arg = zonas_bpm, None

    # Mesma limpeza da exibição no portal antes de o texto virar a nota do
    # workout no relógio: sem isto o aparelho recebe o rótulo de tipo que a IA
    # escreveu ("Tiros — 75 min...") contradizendo o nome do workout, que é o
    # tipo real ("VO2MAX — 2026-08-24"). Também evita reinjetar bpm e cabeçalhos
    # de round-trip que a limpeza já tinha tirado.
    from app.services.plano_semana_service import limpar_descricao_planejada
    descricao = limpar_descricao_planejada(descricao)

    workout = build_cycling_workout(
        tipo, duracao_min, nome, descricao,
        zonas_bpm=bpm_arg, zonas_watts=watts_arg,
        primario="watts" if usar_watts else "fc",
    )
    if not workout:
        logger.warning("Tipo %s não tem builder de workout", tipo)
        return None

    # Resolve o cliente antes de entrar na thread (get_garmin_client é async)
    api = await get_garmin_client(user_id)

    year = int(data_iso[:4])
    month = int(data_iso[5:7])

    def _limpar_data_sync():
        """Remove todos os workouts agendados no Garmin para data_iso (evita duplicatas)."""
        try:
            raw = api.get_scheduled_workouts(year, month) or []
            items = raw.get("calendarItems") or [] if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
            for entry in items:
                if not isinstance(entry, dict):
                    continue
                cal_date = (entry.get("calendarDate") or entry.get("date") or "")[:10]
                if cal_date != data_iso:
                    continue
                if entry.get("itemType") != "workout":
                    continue
                wo = entry.get("workout") or {}
                wid = str(wo.get("workoutId") or entry.get("workoutId") or "")
                if not wid:
                    continue
                try:
                    api.unschedule_workout(wid)
                except Exception:
                    pass
                try:
                    api.delete_workout(wid)
                except Exception:
                    pass
        except Exception as e:
            logger.warning("_limpar_data_sync %s: %s (ignorado)", data_iso, e)

    def _upload() -> str | None:
        _limpar_data_sync()
        try:
            result = api.upload_cycling_workout(workout)
        except Exception as e:
            # Alvo duplo é extensão recente do Garmin — se a conta/API recusar,
            # reenvia só com o alvo primário. Melhor um alvo do que nenhum treino.
            if not _tem_secundario(workout.workoutSegments[0].workoutSteps):
                raise
            logger.warning(
                "Garmin recusou o alvo duplo (%s/%s): %s — reenviando só com o primário",
                tipo, data_iso, e,
            )
            for seg in workout.workoutSegments:
                _sem_secundario(seg.workoutSteps)
            result = api.upload_cycling_workout(workout)
        workout_id = None
        if isinstance(result, dict):
            workout_id = str(result.get("workoutId") or result.get("workout_id") or "")
        elif hasattr(result, "workoutId"):
            workout_id = str(result.workoutId)
        if workout_id:
            api.schedule_workout(workout_id, data_iso)
        return workout_id

    try:
        workout_id = await asyncio.to_thread(_upload)
        logger.info("Workout %s agendado para %s — id=%s", tipo, data_iso, workout_id)
        return workout_id
    except Exception as e:
        logger.error("upload_e_agendar falhou para %s/%s: %s", tipo, data_iso, e)
        return None


async def deletar_workout_garmin(user_id: str, gid: str) -> bool:
    """Remove o workout do Garmin Connect pelo ID.

    Usa api.delete_workout(workout_id) que está disponível na lib garminconnect.
    Também tenta desagendar primeiro (unschedule_workout) pra evitar erro de
    referência pendente — mas segue mesmo se falhar.

    Roda em thread (asyncio.to_thread) para não bloquear o event loop.
    Retorna True se deletou com sucesso, False caso contrário.
    Em caso de falha, loga o erro e NÃO lança exceção, para não derrubar o fluxo
    do webhook — o sync de pull do Garmin irá reconciliar na próxima sincronização.
    """
    if not gid:
        return False

    from app.services.garmin_service import get_garmin_client
    # Resolve o cliente antes de entrar na thread (get_garmin_client é async)
    api = await get_garmin_client(user_id)

    def _delete():
        try:
            # Tenta desagendar primeiro (ignora erro se não encontrar)
            api.unschedule_workout(gid)
        except Exception as e_unsched:
            logger.debug("unschedule_workout %s: %s (ignorado)", gid, e_unsched)
        # Deleta o workout propriamente dito
        api.delete_workout(gid)
        return True

    try:
        ok = await asyncio.to_thread(_delete)
        logger.info("deletar_workout_garmin: id=%s removido (user_id=%s)", gid, user_id)
        return ok
    except Exception as e:
        # Não quebra o fluxo — avisa no log e segue
        logger.warning(
            "deletar_workout_garmin: falha ao remover id=%s (user_id=%s) — %s. "
            "O sync de pull irá reconciliar na próxima sincronização.",
            gid, user_id, e,
        )
        return False
