import re
import statistics
from fitparse import FitFile

# Zonas de FC do Marciano (FC max 192)
Z1_MAX = 134
Z2_MIN, Z2_MAX = 135, 153
Z3_MIN, Z3_MAX = 154, 164
Z4_MIN, Z4_MAX = 165, 177
Z5_MIN = 178


def _count_intervals(values: list, threshold: int, min_run: int = 3) -> int:
    count, in_run, run_len = 0, False, 0
    for v in values:
        if v >= threshold:
            in_run, run_len = True, run_len + 1
        else:
            if in_run and run_len >= min_run:
                count += 1
            in_run, run_len = False, 0
    if in_run and run_len >= min_run:
        count += 1
    return count


def _classify(hr_values: list, avg_power=None, norm_power=None, max_power=None) -> str:
    # 1. Potência — mais confiável para tiros neuromusculares curtos
    if avg_power and norm_power and avg_power > 0:
        vi = norm_power / avg_power  # Variability Index
        if vi >= 1.15:
            return "TIROS"
    if avg_power and max_power and avg_power > 0:
        if max_power / avg_power >= 3.0:
            return "TIROS"

    if not hr_values:
        return "Z2_LONGO"  # arquivo válido mas sem FC → aeróbico por padrão

    total = len(hr_values)
    z1   = sum(1 for h in hr_values if h <= Z1_MAX) / total
    z3   = sum(1 for h in hr_values if Z3_MIN <= h <= Z3_MAX) / total
    z4   = sum(1 for h in hr_values if Z4_MIN <= h <= Z4_MAX) / total
    z5   = sum(1 for h in hr_values if h >= Z5_MIN) / total
    high = z4 + z5
    std  = statistics.stdev(hr_values) if len(hr_values) > 1 else 0

    # 2. Intervalos detectados pela FC
    n_intervals = _count_intervals(hr_values, Z4_MIN, min_run=3)
    if n_intervals >= 2:
        return "TIROS"
    if z5 > 0.01 and std > 8:
        return "TIROS"

    if z5 > 0.15:
        return "VO2MAX"
    if high > 0.30:
        return "TIROS" if std > 15 else "VO2MAX"
    if z3 + z4 > 0.40:
        return "TEMPO"
    if z1 > 0.70 and std < 8:
        return "RECUPERACAO"

    return "Z2_LONGO"


def _extrair_passos_treino(ff) -> list[dict]:
    passos = []
    for msg in ff.get_messages("workout_step"):
        passo = {}
        for field in msg.fields:
            name, val = field.name, field.value
            if val is None:
                continue
            if name == "wkt_step_name":
                passo["nome"] = str(val)
            elif name == "duration_type":
                passo["duracao_tipo"] = str(val)
            elif name == "duration_value":
                passo["duracao_valor"] = val
            elif name == "target_type":
                passo["alvo_tipo"] = str(val)
            elif name == "target_hr_zone":
                passo["zona_fc"] = int(val)
            elif name == "intensity":
                passo["intensidade"] = str(val)
        if passo:
            passos.append(passo)
    return passos


def _passos_para_texto(passos: list[dict], duracao_min: int | None) -> str:
    if not passos:
        return ""
    linhas = []
    for p in passos:
        nome = p.get("nome") or p.get("intensidade", "Passo")
        dur_tipo = p.get("duracao_tipo", "")
        dur_val = p.get("duracao_valor")
        zona = p.get("zona_fc")
        alvo = p.get("alvo_tipo", "")
        dur_str = ""
        if "time" in str(dur_tipo).lower() and dur_val:
            mins = int(dur_val) // 60
            secs = int(dur_val) % 60
            dur_str = f"{mins}:{secs:02d} min"
        zona_str = f"Zona FC {zona}" if zona else (alvo if alvo else "")
        linhas.append(f"- {nome}: {dur_str} {zona_str}".strip())
    total_str = f"Duração total: {duracao_min} min" if duracao_min else ""
    return (total_str + "\n" + "\n".join(linhas)).strip()


def analisar_fit(caminho: str) -> dict:
    ff = FitFile(caminho)

    hr_values       = []
    power_values    = []
    cadence_values  = []
    duration_s      = 0.0
    distance_m      = 0.0
    elevation_m     = 0.0
    calories        = 0
    avg_power       = None
    norm_power      = None
    max_power       = None
    avg_cadence_ses = None

    # Dados agregados da sessão
    for msg in ff.get_messages("session"):
        for field in msg.fields:
            name, val = field.name, field.value
            if val is None:
                continue
            if name == "total_elapsed_time":
                duration_s = float(val)
            elif name == "total_timer_time" and not duration_s:
                duration_s = float(val)
            elif name == "total_distance":
                distance_m = float(val)
            elif name == "total_ascent":
                elevation_m = float(val)
            elif name == "total_calories":
                calories = int(val)
            elif name == "avg_power":
                avg_power = float(val)
            elif name == "normalized_power":
                norm_power = float(val)
            elif name == "max_power":
                max_power = float(val)
            elif name == "avg_cadence":
                avg_cadence_ses = int(val)

    # Registros por segundo
    for msg in ff.get_messages("record"):
        hr = msg.get_value("heart_rate")
        if hr is not None:
            hr_values.append(int(hr))
        pw = msg.get_value("power")
        if pw is not None:
            power_values.append(int(pw))
        cad = msg.get_value("cadence")
        if cad is not None and int(cad) > 0:
            cadence_values.append(int(cad))

    # Fallbacks: duração e potência a partir dos records
    if not duration_s and hr_values:
        duration_s = float(len(hr_values))   # ~1 registro/seg

    if power_values:
        if avg_power is None:
            avg_power = sum(power_values) / len(power_values)
        if max_power is None:
            max_power = float(max(power_values))

    duration_min = max(1, round(duration_s / 60)) if duration_s else None

    tipo = _classify(hr_values, avg_power, norm_power, max_power)

    avg_hr = round(sum(hr_values) / len(hr_values)) if hr_values else None
    max_hr = max(hr_values) if hr_values else None

    passos = _extrair_passos_treino(ff)
    descricao_estruturada = _passos_para_texto(passos, duration_min)

    workout_name = None
    workout_notes = None
    for msg in ff.get_messages("workout"):
        wn = msg.get_value("wkt_name")
        if wn:
            workout_name = str(wn)
        for field in msg.fields:
            if field.name == "unknown_17" and field.value:
                workout_notes = str(field.value)
        break

    # Cadência: 1) média da sessão/records; 2) extrai do texto da descrição
    cadencia_rpm = None
    if avg_cadence_ses and avg_cadence_ses > 0:
        cadencia_rpm = str(avg_cadence_ses)
    elif cadence_values:
        avg_cad = round(sum(cadence_values) / len(cadence_values))
        cadencia_rpm = str(avg_cad)
    else:
        texto = (descricao_estruturada or "") + " " + (workout_name or "")
        m = re.search(r'(\d{2,3})\s*[-–]\s*(\d{2,3})\s*rpm', texto, re.IGNORECASE)
        if m:
            cadencia_rpm = f"{m.group(1)}-{m.group(2)}"
        else:
            m2 = re.search(r'(\d{2,3})\s*rpm', texto, re.IGNORECASE)
            if m2:
                cadencia_rpm = m2.group(1)

    return {
        "tipo":                   tipo,
        "duracao_min":            duration_min,
        "distancia_km":           round(distance_m / 1000, 2) if distance_m else None,
        "elevacao_m":             round(elevation_m) if elevation_m else None,
        "calorias":               calories or None,
        "avg_hr":                 avg_hr,
        "max_hr":                 max_hr,
        "cadencia_rpm":           cadencia_rpm,
        "workout_name":           workout_name,
        "workout_notes":          workout_notes,
        "descricao_estruturada":  descricao_estruturada or None,
    }
