"""Builders de CyclingWorkout para o Garmin Connect.

Zonas de FC configuradas no Garmin do Marciano:
  Z1: 123-145 bpm  (Aquecimento)
  Z2: 146-158 bpm  (Fácil)
  Z3: 159-165 bpm  (Aeróbico)
  Z4: 166-177 bpm  (Limite)
  Z5: >177 bpm     (Máximo)
FCmáx: 190 | Limiar de lactato: 172
"""

import asyncio
import logging
from datetime import datetime

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


def _seg(steps: list) -> WorkoutSegment:
    return WorkoutSegment(segmentOrder=1, sportType=_CYCLING_SPORT, workoutSteps=steps)


def _aplicar_bpm(steps: list, zonas_bpm: dict) -> None:
    """Converte os alvos de zona (1-5) em faixas de bpm explícitas, lendo as
    zonas configuradas pelo usuário. Os valores ficam no nível do step
    (targetValueOne/Two), que é o formato que o Garmin espera. Recursivo para
    entrar nos repeat groups."""
    for step in steps:
        filhos = getattr(step, "workoutSteps", None)
        if filhos:
            _aplicar_bpm(filhos, zonas_bpm)
            continue
        tt = getattr(step, "targetType", None)
        if not tt or tt.get("workoutTargetTypeId") != TargetType.HEART_RATE:
            continue
        zona = tt.get("targetValue")
        rng = zonas_bpm.get(zona)
        if rng:
            step.targetType = {
                "workoutTargetTypeId": TargetType.HEART_RATE,
                "workoutTargetTypeKey": "heart.rate",
                "displayOrder": 1,
            }
            step.targetValueOne = float(rng["min"])
            step.targetValueTwo = float(rng["max"])
        else:
            # sem faixa configurada: cai na zona do próprio dispositivo
            step.targetType = {
                "workoutTargetTypeId": TargetType.HEART_RATE,
                "workoutTargetTypeKey": "heart.rate.zone",
                "displayOrder": 1,
                "zoneNumber": zona,
            }


# ── builders por TipoTreino ───────────────────────────────────────────────────

def _recuperacao(duracao_min: int = 55) -> tuple[list, int]:
    """Z1 contínuo — recuperação ativa."""
    main_s = max(600, (duracao_min - 20) * 60)
    steps = [
        create_warmup_step(600, step_order=1, target_type=_hz(1)),
        create_interval_step(main_s, step_order=2, target_type=_hz(1)),
        create_cooldown_step(600, step_order=3, target_type=_hz(1)),
    ]
    total = 1200 + main_s
    return steps, total


def _z2_longo(duracao_min: int = 120) -> tuple[list, int]:
    """Z2 sustentado — base aeróbica."""
    main_s = max(1800, (duracao_min - 30) * 60)
    steps = [
        create_warmup_step(900, step_order=1, target_type=_hz(1)),
        create_interval_step(main_s, step_order=2, target_type=_hz(2)),
        create_cooldown_step(900, step_order=3, target_type=_hz(1)),
    ]
    total = 1800 + main_s
    return steps, total


def _tempo(duracao_min: int = 70) -> tuple[list, int]:
    """3x10 min Z3 com recuperação Z2 — esforço de limiar."""
    reps = 3
    interval_s = 600    # 10 min Z3
    recovery_s = 300    # 5 min Z2
    inner = [
        create_interval_step(interval_s, step_order=1, target_type=_hz(3)),
        create_recovery_step(recovery_s, step_order=2, target_type=_hz(2)),
    ]
    steps = [
        create_warmup_step(900, step_order=1, target_type=_hz(2)),
        create_repeat_group(reps, inner, step_order=2),
        create_cooldown_step(600, step_order=3, target_type=_hz(2)),
    ]
    total = 900 + reps * (interval_s + recovery_s) + 600
    return steps, total


def _forca(duracao_min: int = 65) -> tuple[list, int]:
    """4x6 min Z3 cadência baixa — força específica."""
    reps = 4
    interval_s = 360    # 6 min Z3 (cadência 50-60 rpm)
    recovery_s = 240    # 4 min Z2
    inner = [
        create_interval_step(interval_s, step_order=1, target_type=_hz(3)),
        create_recovery_step(recovery_s, step_order=2, target_type=_hz(2)),
    ]
    steps = [
        create_warmup_step(900, step_order=1, target_type=_hz(2)),
        create_repeat_group(reps, inner, step_order=2),
        create_cooldown_step(600, step_order=3, target_type=_hz(2)),
    ]
    total = 900 + reps * (interval_s + recovery_s) + 600
    return steps, total


def _tiros(duracao_min: int = 62) -> tuple[list, int]:
    """8x30s Z5 com recuperação Z1 — sprints neuromusculares."""
    reps = 8
    interval_s = 30     # 30s Z5
    recovery_s = 210    # 3.5 min Z1
    inner = [
        create_interval_step(interval_s, step_order=1, target_type=_hz(5)),
        create_recovery_step(recovery_s, step_order=2, target_type=_hz(1)),
    ]
    steps = [
        create_warmup_step(900, step_order=1, target_type=_hz(2)),
        create_repeat_group(reps, inner, step_order=2),
        create_cooldown_step(900, step_order=3, target_type=_hz(2)),
    ]
    total = 900 + reps * (interval_s + recovery_s) + 900
    return steps, total


def _vo2max(duracao_min: int = 62) -> tuple[list, int]:
    """4x4 min Z4-Z5 com recuperação Z2 — VO2max."""
    reps = 4
    interval_s = 240    # 4 min Z5
    recovery_s = 240    # 4 min Z2
    inner = [
        create_interval_step(interval_s, step_order=1, target_type=_hz(5)),
        create_recovery_step(recovery_s, step_order=2, target_type=_hz(2)),
    ]
    steps = [
        create_warmup_step(900, step_order=1, target_type=_hz(2)),
        create_repeat_group(reps, inner, step_order=2),
        create_cooldown_step(900, step_order=3, target_type=_hz(2)),
    ]
    total = 900 + reps * (interval_s + recovery_s) + 900
    return steps, total


_BUILDERS = {
    "RECUPERACAO": _recuperacao,
    "Z2_LONGO":    _z2_longo,
    "TEMPO":       _tempo,
    "FORCA":       _forca,
    "TIROS":       _tiros,
    "VO2MAX":      _vo2max,
}

_DESCRICOES_PADRAO = {
    "RECUPERACAO": "Pedal leve em Z1. Recuperação ativa, mantenha FC abaixo de 145 bpm.",
    "Z2_LONGO":    "Base aeróbica em Z2 (146-158 bpm). Cadência: 85-95 rpm. Esforço controlado.",
    "TEMPO":       "3x10 min em Z3 (159-165 bpm) com 5 min de recuperação Z2. Esforço moderado-alto sustentado.",
    "FORCA":       "4x6 min em Z3 (159-165 bpm) com cadência baixa (50-60 rpm). 4 min recuperação Z2 entre blocos.",
    "TIROS":       "8x30s em Z5 (>177 bpm) com 3.5 min recuperação Z1. Sprints máximos.",
    "VO2MAX":      "4x4 min em Z5 (>177 bpm) com 4 min recuperação Z2. Esforço VO2max sustentado.",
}


def build_cycling_workout(
    tipo: str,
    duracao_min: int,
    nome: str,
    descricao: str | None = None,
    zonas_bpm: dict | None = None,
) -> CyclingWorkout | None:
    """Monta um CyclingWorkout para o tipo e duração dados.

    Se 'zonas_bpm' for fornecido ({zona: {'min','max'}}), os alvos de FC são
    enviados como faixas de bpm explícitas em vez de número de zona do dispositivo.
    """
    builder = _BUILDERS.get(tipo)
    if not builder:
        return None

    steps, total_s = builder(duracao_min)
    if zonas_bpm:
        _aplicar_bpm(steps, zonas_bpm)
    return CyclingWorkout(
        workoutName=nome,
        estimatedDurationInSecs=total_s,
        description=descricao or _DESCRICOES_PADRAO.get(tipo, ""),
        workoutSegments=[_seg(steps)],
    )


async def upload_e_agendar(
    user_id: str,
    tipo: str,
    duracao_min: int,
    nome: str,
    data_iso: str,
    descricao: str | None = None,
) -> str | None:
    """Faz upload do workout e agenda para a data. Retorna o garmin_workout_id."""
    from app.services.garmin_service import get_garmin_client
    from app.services.config_service import zonas_bpm_map

    zonas_bpm = await zonas_bpm_map(user_id)
    workout = build_cycling_workout(tipo, duracao_min, nome, descricao, zonas_bpm)
    if not workout:
        logger.warning("Tipo %s não tem builder de workout", tipo)
        return None

    # Resolve o cliente antes de entrar na thread (get_garmin_client é async)
    api = await get_garmin_client(user_id)

    def _upload() -> str | None:
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
