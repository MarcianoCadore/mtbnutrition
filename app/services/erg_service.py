"""Exportação de treinos no formato ERG/XML (home trainer indoor).

Gera um XML estruturado no mesmo espírito das plataformas profissionais (Zwift,
TrainerRoad, MyWhoosh, Rouvy): os BLOCOS de potência (`<WorkoutSteps>`) ficam
SEPARADOS dos EVENTOS (`<Events>`). Assim um software de terceiros (o portal do
amigo) pode ler os eventos e exibi-los N segundos ANTES da mudança — sem precisar
inspecionar a árvore de steps.

A fonte dos blocos é a MESMA usada para montar o workout enviado ao Garmin
(`garmin_workout_service.preview_estrutura` → `_BUILDERS`), então o ERG nunca
diverge do que o atleta recebe no relógio. As potências saem em watts absolutos
das zonas do atleta (requer FTP configurado).

Tipos de evento suportados no XML (o cliente decide como renderizar cada um):
    Message   → texto na tela.
    Beep      → alerta sonoro.
    Countdown → contagem regressiva antes de um esforço curto/intenso.
    Voice     → texto para sintetizador de voz.
    Lap       → marca uma volta automática para análise posterior.
    (Color/Overlay ficam a cargo do cliente; o formato é aberto para novos tipos.)
"""

from __future__ import annotations

from xml.sax.saxutils import escape, quoteattr

from app.services.garmin_workout_service import preview_estrutura

# Antecipação padrão (segundos) das mensagens antes de cada bloco.
ANTECIPACAO_PADRAO_S = 15

# Descrição padrão por tipo (fallback quando o treino não traz uma própria).
_DESCRICOES = {
    "RECUPERACAO": "Pedal leve em Z1. Recuperação ativa.",
    "Z2_LONGO":    "Base aeróbica em Z2, esforço controlado.",
    "TEMPO":       "Blocos de Z3 (tempo/ritmo) com recuperação em Z2.",
    "FORCA":       "Blocos de força em Z3 com cadência baixa (50-60 rpm).",
    "TIROS":       "Sprints máximos em Z5 com recuperação longa em Z1.",
    "VO2MAX":      "Intervalos de VO₂máx em Z5 com recuperação em Z2.",
    "TESTE_FTP":   "Protocolo de teste de FTP — esforço máximo sustentável de 20 min.",
}

# Rótulo do bloco por fase; para 'interval' o rótulo depende da zona.
_LABEL_FASE = {"warmup": "Aquecimento", "cooldown": "Volta à calma", "recovery": "Recuperação"}
_LABEL_ZONA_INTERVAL = {
    1: "Leve Z1", 2: "Ritmo Z2", 3: "Bloco Z3", 4: "Limiar Z4", 5: "Esforço Z5",
}


def _fmt_dur(segundos: int) -> str:
    """Duração legível: 30s, 1min, 1min30s, 10min."""
    m, s = divmod(int(segundos), 60)
    if m and s:
        return f"{m}min{s}s"
    if m:
        return f"{m}min"
    return f"{s}s"


def _ramp_bounds(min_w: int, max_w: int, subindo: bool) -> tuple[int, int]:
    """Extremos (start, end) de uma rampa de aquecimento/volta à calma.

    A Z1 do atleta costuma começar em 0 W (0-55% do FTP); uma rampa começando em
    0 W não faz sentido no rolo. Então usamos um piso derivado do topo da zona.
    """
    piso = round(max_w * 0.45) or 1
    baixo = min_w if min_w >= piso else piso
    return (baixo, max_w) if subindo else (max_w, baixo)


def _rotulo_base(fase: str, zona: int | None) -> str:
    """Rótulo do bloco por fase (para 'interval' depende da zona)."""
    if fase == "interval":
        return _LABEL_ZONA_INTERVAL.get(zona or 0, f"Esforço Z{zona}" if zona else "Esforço")
    return _LABEL_FASE.get(fase, fase.capitalize())


def build_erg_xml(
    tipo: str,
    duracao_min: int,
    *,
    zonas_watts: dict,
    nome: str | None = None,
    descricao: str | None = None,
    ftp: int | None = None,
    autor: str = "IA Performance",
    antecipacao_s: int = ANTECIPACAO_PADRAO_S,
    version: str = "1.1",
) -> str | None:
    """Monta o XML ERG do treino `tipo`/`duracao_min` com potências do atleta.

    Retorna a string XML, ou None se o tipo não tiver estrutura (sem builder).
    Requer `zonas_watts` = {zona: {'min','max',...}} (do FTP do atleta) — as
    potências saem em watts absolutos.
    """
    dados = preview_estrutura(tipo, duracao_min, zonas_bpm=None, zonas_watts=zonas_watts)
    if dados is None:
        return None

    segmentos = dados["segments"]
    nome = nome or tipo.replace("_", " ").title()
    descricao = descricao or _DESCRICOES.get(tipo, "Treino estruturado indoor.")

    steps_xml: list[str] = []
    eventos: list[str] = []
    # Pré-conta ocorrências de cada rótulo para só numerar os que se repetem
    # ("Recuperação 1/2/3" quando há várias; "Aquecimento" sozinho fica sem número).
    ocorrencias: dict[str, int] = {}
    for seg in segmentos:
        base = _rotulo_base(seg["fase"], seg["zona"])
        ocorrencias[base] = ocorrencias.get(base, 0) + 1

    usados: dict[str, int] = {}
    step_id = 0
    total = len(segmentos)
    for seg in segmentos:
        step_id += 1
        fase = seg["fase"]
        zona = seg["zona"]
        dur = int(seg["duracao_s"] or 0)
        mn = int(seg["min"] or 0)
        mx = int(seg["max"] or mn)

        base = _rotulo_base(fase, zona)
        if ocorrencias.get(base, 0) > 1:
            usados[base] = usados.get(base, 0) + 1
            step_nome = f"{base} {usados[base]}"
        else:
            step_nome = base

        if fase in ("warmup", "cooldown"):
            start_w, end_w = _ramp_bounds(mn, mx, subindo=(fase == "warmup"))
            steps_xml.append(
                f'        <Ramp Id="{step_id}" Name={quoteattr(step_nome)} '
                f'Duration="{dur}" StartPower="{start_w}" EndPower="{end_w}"/>'
            )
            if fase == "warmup":
                texto = f"Aquecimento progressivo de {start_w} a {end_w} watts por {_fmt_dur(dur)}."
            else:
                texto = f"Volta à calma: de {start_w} a {end_w} watts por {_fmt_dur(dur)}."
        else:
            power = round((mn + mx) / 2) if mx else mn
            steps_xml.append(
                f'        <Steady Id="{step_id}" Name={quoteattr(step_nome)} '
                f'Duration="{dur}" Power="{power}"/>'
            )
            texto = f"Em {antecipacao_s}s: {step_nome} — {_fmt_dur(dur)} a {power} watts."

        # ── eventos DESACOPLADOS deste step ─────────────────────────────────────
        # Mensagem de antecipação (N s antes do início do bloco).
        eventos.append(
            f'        <Event StepId="{step_id}" Offset="-{antecipacao_s}" '
            f'Type="Message" Text={quoteattr(texto)}/>'
        )
        # Esforços curtos e intensos ganham contagem regressiva + beep no início.
        intenso = (zona or 0) >= 4
        if intenso and dur <= 60:
            eventos.append(
                f'        <Event StepId="{step_id}" Offset="-{antecipacao_s}" Type="Countdown"/>'
            )
        if intenso:
            eventos.append(f'        <Event StepId="{step_id}" Offset="0" Type="Beep"/>')
        # Marca volta automática no início de cada esforço principal (para análise).
        if fase == "interval":
            eventos.append(f'        <Event StepId="{step_id}" Offset="0" Type="Lap"/>')

    # Evento final: parabeniza perto do fim do último bloco.
    if segmentos:
        ult_dur = int(segmentos[-1]["duracao_s"] or 0)
        off = max(0, ult_dur - antecipacao_s)
        eventos.append(
            f'        <Event StepId="{total}" Offset="{off}" '
            f'Type="Message" Text="Treino concluído. Parabéns!"/>'
        )

    ftp_line = f"\n        <Ftp>{int(ftp)}</Ftp>" if ftp else ""

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<Workout name={quoteattr(nome)} version="{version}">\n\n'
        '    <Metadata>\n'
        f'        <Author>{escape(autor)}</Author>\n'
        f'        <Description>{escape(descricao)}</Description>{ftp_line}\n'
        '    </Metadata>\n\n'
        '    <WorkoutSteps>\n\n'
        + "\n\n".join(steps_xml)
        + '\n\n    </WorkoutSteps>\n\n'
        '    <Events>\n\n'
        + "\n\n".join(eventos)
        + '\n\n    </Events>\n\n'
        '</Workout>\n'
    )
