import re
import statistics
from fitparse import FitFile

def _fracao_por_zona(valores: list, zonas: dict | None) -> dict:
    """Fração do tempo em cada zona, com as faixas DO ATLETA.

    `zonas` = {numero: {"min":.., "max":..}} — de config_service.zonas_bpm_map
    (FC) ou zonas_watts_map (potência). Abaixo da primeira zona conta como a
    primeira; acima da última, como a última.
    """
    if not valores or not zonas:
        return {}
    faixas = sorted(zonas.items())
    contagem = {z: 0 for z, _ in faixas}
    for v in valores:
        if v <= faixas[0][1]["max"]:
            contagem[faixas[0][0]] += 1
        elif v >= faixas[-1][1]["min"]:
            contagem[faixas[-1][0]] += 1
        else:
            for z, faixa in faixas:
                if faixa["min"] <= v <= faixa["max"]:
                    contagem[z] += 1
                    break
    total = len(valores)
    return {z: c / total for z, c in contagem.items()}


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


def _classify(hr_values: list, zonas_bpm: dict | None = None,
              avg_power=None, norm_power=None, max_power=None,
              power_values: list | None = None, zonas_watts: dict | None = None,
              ignorar_fc: bool = False) -> str:
    """Que tipo de treino esta sessão FOI, pela distribuição de intensidade.

    As faixas vêm das zonas do atleta (`zonas_bpm`/`zonas_watts`), lidas na hora
    da classificação: cada um tem as suas, e as de um mesmo atleta mudam com o
    tempo (novo teste de FC/FTP). Nada de bpm fixo aqui — com faixa de outra
    pessoa, um Z2 vira VO2máx.

    Quando a FC não é confiável (`ignorar_fc`: sem cinta, cinta falhando) a
    leitura é feita pelos watts, que no rolo são o dado bom. Sem nenhum dos dois,
    sobra o padrão aeróbico.
    """
    # 1. Potência — mais confiável para tiros neuromusculares curtos, e não
    #    depende de zona: é a forma da sessão (picos sobre a média).
    if avg_power and norm_power and avg_power > 0:
        vi = norm_power / avg_power  # Variability Index
        if vi >= 1.15:
            return "TIROS"
    if avg_power and max_power and avg_power > 0:
        if max_power / avg_power >= 3.0:
            return "TIROS"

    # 2. Distribuição nas zonas do atleta.
    usa_fc = bool(hr_values and zonas_bpm and not ignorar_fc)
    if usa_fc:
        return _classify_fc(hr_values, zonas_bpm)
    return _classify_watts(power_values, zonas_watts)


def _classify_fc(hr_values: list, zonas_bpm: dict) -> str:
    fr = _fracao_por_zona(hr_values, zonas_bpm)
    if not fr:
        return "Z2_LONGO"
    z1, z3, z4, z5 = fr.get(1, 0), fr.get(3, 0), fr.get(4, 0), fr.get(5, 0)
    high = z4 + z5
    std = statistics.stdev(hr_values) if len(hr_values) > 1 else 0

    # Intervalos detectados pela FC: entradas em Z4 separadas por recuperação.
    n_intervals = _count_intervals(hr_values, zonas_bpm[4]["min"], min_run=3)
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


def _classify_watts(power_values: list | None, zonas_watts: dict | None) -> str:
    """Leitura por potência, para quando a FC não serve.

    As zonas de potência são as 7 de Coggan (config_service.calc_zonas_potencia):
    Z5 é o VO2máx, Z6/Z7 é o anaeróbico/neuromuscular dos tiros. Sem heurística de
    desvio-padrão aqui — em watts a variação é natural até em Z2, e picos curtos
    já foram tratados pelo Variability Index acima.
    """
    fr = _fracao_por_zona(power_values, zonas_watts)
    if not fr:
        return "Z2_LONGO"  # arquivo válido mas sem dado utilizável → aeróbico
    acima_do_limiar = sum(v for z, v in fr.items() if z >= 5)
    if acima_do_limiar > 0.10:
        return "VO2MAX"
    if fr.get(4, 0) + fr.get(3, 0) > 0.40:
        return "TEMPO"
    if fr.get(1, 0) > 0.70:
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


def hrtss_ponderado(caminho: str, limiar) -> int | None:
    """TSS estimado integrando (FC/limiar)² a cada segundo do treino.

    Mais fiel que usar só a FC média: como integra o quadrado da intensidade
    amostra a amostra, dá o peso certo a quem fez tiros de verdade (picos em Z4/Z5
    elevam o TSS) e a quem ficou em Z2 (intensidade baixa puxa para baixo). Assume
    ~1 amostra/segundo, como nos .fit do Garmin.
    """
    if not limiar:
        return None
    try:
        ff = FitFile(caminho)
        soma = 0.0
        n = 0
        for msg in ff.get_messages("record"):
            hr = msg.get_value("heart_rate")
            if hr is not None:
                soma += (int(hr) / limiar) ** 2
                n += 1
    except Exception:
        return None
    if not n:
        return None
    # TSS = horas × média(IF²) × 100 = (n/3600) × (soma/n) × 100 = soma×100/3600
    return round(soma * 100 / 3600)


def tempo_em_zonas(caminho: str, zonas: list[dict]) -> dict | None:
    """Tempo (em segundos) em cada zona de FC, lido segundo-a-segundo do .fit.

    `zonas` = [{"zona":1,"min":..,"max":..}, ...] (faixas configuradas do atleta).
    Diferente da FC média, mostra a real distribuição de intensidade — essencial
    em treinos de tiros, onde a média é diluída por aquecimento, recuperações
    entre os tiros e volta à calma. Retorna {1: seg, ..., 5: seg} ou None.
    """
    if not zonas:
        return None
    try:
        ff = FitFile(caminho)
    except Exception:
        return None
    zs = sorted(zonas, key=lambda z: z["min"])
    contagem = {z["zona"]: 0 for z in zs}
    n = 0
    for msg in ff.get_messages("record"):
        hr = msg.get_value("heart_rate")
        if hr is None:
            continue
        hr = int(hr)
        n += 1
        if hr <= zs[0]["max"]:            # abaixo/dentro da primeira zona
            contagem[zs[0]["zona"]] += 1
        elif hr >= zs[-1]["min"]:         # dentro/acima da última zona
            contagem[zs[-1]["zona"]] += 1
        else:
            for z in zs:
                if z["min"] <= hr <= z["max"]:
                    contagem[z["zona"]] += 1
                    break
    if not n:
        return None
    return contagem  # ~1 amostra/segundo nos .fit do Garmin


def tempo_em_zonas_potencia(caminho: str, zonas: list[dict]) -> dict | None:
    """Tempo (em segundos) em cada zona de potência, lido segundo-a-segundo do .fit.

    `zonas` = [{"zona":1,"min":0,"max":110}, ...] (7 faixas em watts).
    Retorna {1: seg, ..., 7: seg} ou None se não houver dados de potência.
    Ignora amostras de 0W (coasting/pausa) para não inflar Z1.
    """
    if not zonas:
        return None
    try:
        ff = FitFile(caminho)
    except Exception:
        return None
    zs = sorted(zonas, key=lambda z: z["min"])
    contagem = {z["zona"]: 0 for z in zs}
    n = 0
    for msg in ff.get_messages("record"):
        pw = msg.get_value("power")
        if pw is None or int(pw) <= 0:
            continue
        pw = int(pw)
        n += 1
        if pw <= zs[0]["max"]:
            contagem[zs[0]["zona"]] += 1
        elif pw >= zs[-1]["min"]:
            contagem[zs[-1]["zona"]] += 1
        else:
            for z in zs:
                if z["min"] <= pw <= z["max"]:
                    contagem[z["zona"]] += 1
                    break
    if not n:
        return None
    return contagem


# ── Curva de potência ────────────────────────────────────────────────────────
# Durações que o ciclista reconhece: pico de sprint, capacidade anaeróbia,
# VO2max e limiar. A de 1200s (20min) é a que estima o FTP.
DURACOES_CURVA = (5, 15, 60, 300, 600, 1200)


def melhores_esforcos(power_values: list[int],
                      duracoes: tuple[int, ...] = DURACOES_CURVA) -> dict[int, int]:
    """Melhor potência média sustentada em cada janela, em watts.

    Soma móvel em O(n) por duração — um treino de 4h tem ~14 mil amostras e
    isto roda no sync, então força bruta não serve.

    Assume 1 amostra por segundo, que é o que o Garmin grava. Um arquivo com
    "smart recording" (amostragem variável) superestima um pouco a janela; é
    aceitável para estimar FTP e é como o resto do mercado trata o caso.
    """
    if not power_values:
        return {}

    n = len(power_values)
    saida: dict[int, int] = {}
    for dur in duracoes:
        if n < dur:
            continue
        soma = sum(power_values[:dur])
        melhor = soma
        for i in range(dur, n):
            soma += power_values[i] - power_values[i - dur]
            if soma > melhor:
                melhor = soma
        saida[dur] = round(melhor / dur)
    return saida


def curva_de_potencia(caminho: str) -> dict[int, int]:
    """Melhores esforços de um arquivo .fit. {} se não houver potência."""
    valores = []
    for msg in FitFile(caminho).get_messages("record"):
        pw = msg.get_value("power")
        if pw is not None:
            valores.append(int(pw))
    return melhores_esforcos(valores)


def ptss(norm_power: float | None, ftp: int, duracao_min: int | None) -> int | None:
    """Power TSS = (duracao_h × NP × IF) / (FTP × 3600) × 10000, onde IF = NP/FTP.
    Equivalente a: (duracao_s × IF²) / 3600 × 100.
    """
    if not (norm_power and ftp and duracao_min):
        return None
    if_fator = norm_power / ftp
    return round((duracao_min / 60) * (if_fator ** 2) * 100)


def analisar_fit(caminho: str, zonas_bpm: dict | None = None,
                 zonas_watts: dict | None = None, ignorar_fc: bool = False) -> dict:
    """Lê o .fit e devolve as métricas da sessão + o tipo de treino que ela foi.

    `zonas_bpm`/`zonas_watts` são as faixas ATUAIS do atleta (config_service):
    sem elas o tipo não é classificado por intensidade, só pela forma da curva de
    potência. `ignorar_fc` manda ler pelos watts quando a FC daquele treino não é
    confiável (ver avaliacao_service.deve_ignorar_fc).
    """
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

    tipo = _classify(hr_values, zonas_bpm, avg_power, norm_power, max_power,
                     power_values=power_values, zonas_watts=zonas_watts,
                     ignorar_fc=ignorar_fc)

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
        "avg_power":              round(avg_power) if avg_power else None,
        "norm_power":             round(norm_power) if norm_power else None,
        "cadencia_rpm":           cadencia_rpm,
        "workout_name":           workout_name,
        "workout_notes":          workout_notes,
        "descricao_estruturada":  descricao_estruturada or None,
    }
