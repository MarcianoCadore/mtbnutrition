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


def _aplicar_watts(steps: list, zonas_watts: dict) -> None:
    """Substitui o target de FC por target de potência (watts explícitos) em todos os steps.

    `zonas_watts` = {1: {min, max}, ..., 7: {min, max}} mapeado por zona de potência.
    A zona de potência é derivada da zona de FC original do step (via _pw).
    Recursivo para entrar nos repeat groups.
    """
    for step in steps:
        filhos = getattr(step, "workoutSteps", None)
        if filhos:
            _aplicar_watts(filhos, zonas_watts)
            continue
        tt = getattr(step, "targetType", None)
        if not tt or tt.get("workoutTargetTypeId") != TargetType.HEART_RATE:
            continue
        zona_fc = tt.get("targetValue")
        zona_p = _pw(zona_fc) if zona_fc else None
        rng = zonas_watts.get(zona_p) if zona_p else None
        if not rng:
            continue
        step.targetType = {
            "workoutTargetTypeId": TargetType.POWER,
            "workoutTargetTypeKey": "power",
            "displayOrder": 1,
        }
        step.targetValueOne = float(rng["min"])
        step.targetValueTwo = float(rng["max"]) if rng["max"] < 9000 else float(rng["min"] * 2)


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


def _teste_ftp(duracao_min: int = 57) -> tuple[list, int]:
    """Protocolo completo de teste FTP de 20min."""
    # Aquecimento Z1 — 10min
    # Progressivo Z3 — 5min
    # 3x (30seg Z5 + 1min Z1 recuperação)
    # Pré-teste Z1 — 2min suave
    # TESTE FTP Z4 — 20min potência máxima sustentável
    # Desaquecimento Z1 — 15min
    inner_acel = [
        create_interval_step(30, step_order=1, target_type=_hz(5)),
        create_recovery_step(60, step_order=2, target_type=_hz(1)),
    ]
    steps = [
        create_warmup_step(600, step_order=1, target_type=_hz(1)),         # 10min Z1
        create_interval_step(300, step_order=2, target_type=_hz(3)),       # 5min Z3 progressivo
        create_repeat_group(3, inner_acel, step_order=3),                  # 3x aceleração
        create_interval_step(120, step_order=4, target_type=_hz(1)),       # 2min Z1 pré-teste
        create_interval_step(1200, step_order=5, target_type=_hz(4)),      # 20min TESTE FTP Z4
        create_cooldown_step(900, step_order=6, target_type=_hz(1)),       # 15min Z1
    ]
    total = 600 + 300 + 3 * (30 + 60) + 120 + 1200 + 900
    return steps, total


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
    forcar_indoor: bool | None = None,
) -> str | None:
    """Faz upload do workout e agenda para a data. Retorna o garmin_workout_id.

    forcar_indoor:
      True  → força alvos em watts (usuário marcou "indoor" no dia)
      False → força alvos em FC (usuário marcou "outdoor" no dia)
      None  → usa a lógica do potencia_modo + tipo (comportamento padrão)
    """
    from app.services.garmin_service import get_garmin_client
    from app.services.config_service import zonas_bpm_map, get_zonas_potencia

    # Determina se vai usar watts ANTES de montar o workout para evitar que
    # _aplicar_bpm remova o targetValue (número de zona) que _aplicar_watts precisa.
    zp = await get_zonas_potencia(user_id)
    usar_watts = False
    if zp:
        if forcar_indoor is True:
            usar_watts = True
        elif forcar_indoor is False:
            usar_watts = False
        else:
            modo = zp.get("potencia_modo", "indoor")
            usar_watts = (modo == "sempre") or (modo == "indoor" and tipo in _TIPOS_INDOOR)

    zonas_bpm = await zonas_bpm_map(user_id)
    # Não aplica BPM explícito se vai usar watts — _aplicar_bpm remove o targetValue
    # (número de zona) que _aplicar_watts precisa para mapear para watts.
    workout = build_cycling_workout(tipo, duracao_min, nome, descricao, zonas_bpm if not usar_watts else None)
    if not workout:
        logger.warning("Tipo %s não tem builder de workout", tipo)
        return None

    if usar_watts:
        zonas_w = {z["zona"]: {"min": z["min"], "max": z["max"]} for z in zp["zonas"]}
        for seg in workout.workoutSegments:
            _aplicar_watts(seg.workoutSteps, zonas_w)

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
