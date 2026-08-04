"""Exportação de treinos no formato .zwo (Zwift Workout).

O .zwo é o padrão de fato dos apps de home trainer (Zwift, TrainerRoad, MyWhoosh,
Rouvy…): a potência é expressa como **fração do FTP** (0.75 = 75% do FTP), então
o arquivo é RELATIVO — cada atleta baixa o seu e o próprio software escala pelo
FTP dele. Por isso a exportação não exige FTP configurado no nosso app.

A fonte da estrutura é a MESMA usada para o Garmin (`preview_estrutura` →
`_BUILDERS`): fase (warmup/interval/recovery/cooldown), zona (1-5) e duração de
cada bloco. As porcentagens de FTP por zona vêm de `config_service.faixa_util_pct`
(bandas Coggan com piso prescritível), então o .zwo nunca diverge da prescrição.

Mensagens seguem o esquema do Zwift: `<textevent timeoffset=... message=...>`
aninhado no bloco. Para o aviso "faltam 15 s", o texto é colocado no fim do bloco
ATUAL anunciando o PRÓXIMO — o cliente exibe no tempo certo.
"""

from __future__ import annotations

from xml.sax.saxutils import escape, quoteattr

from app.services.garmin_workout_service import preview_estrutura
from app.services.config_service import faixa_util_pct

ANTECIPACAO_PADRAO_S = 15

_DESCRICOES = {
    "RECUPERACAO": "Pedal leve em Z1. Recuperação ativa.",
    "Z2_LONGO":    "Base aeróbica em Z2, esforço controlado.",
    "TEMPO":       "Blocos de Z3 (tempo/ritmo) com recuperação em Z2.",
    "FORCA":       "Blocos de força em Z3 com cadência baixa (50-60 rpm).",
    "TIROS":       "Sprints máximos em Z5 com recuperação longa em Z1.",
    "VO2MAX":      "Intervalos de VO₂máx em Z5 com recuperação em Z2.",
    "TESTE_FTP":   "Protocolo de teste de FTP — esforço máximo sustentável de 20 min.",
}

_LABEL_FASE = {"warmup": "Aquecimento", "cooldown": "Volta à calma", "recovery": "Recuperação"}
_LABEL_ZONA = {1: "Leve Z1", 2: "Ritmo Z2", 3: "Bloco Z3", 4: "Limiar Z4", 5: "Esforço Z5"}


def _rotulo(fase: str, zona: int | None) -> str:
    if fase == "interval":
        return _LABEL_ZONA.get(zona or 0, f"Esforço Z{zona}" if zona else "Esforço")
    return _LABEL_FASE.get(fase, fase.capitalize())


def _num(v: float) -> str:
    """Formata a fração de FTP de forma enxuta (0.55, 1.13)."""
    return f"{round(v, 3):g}"


def _fmt_dur(segundos: int) -> str:
    m, s = divmod(int(segundos), 60)
    if m and s:
        return f"{m}min{s}s"
    return f"{m}min" if m else f"{s}s"


def _mid_pct(zona: int | None) -> float:
    """Potência-alvo de um bloco fixo da zona (meio da faixa prescritível)."""
    lo, hi = faixa_util_pct(zona or 0)
    return (lo + hi) / 2


def _ramp_pct(zona: int | None) -> tuple[float, float]:
    """(piso, alvo) da rampa de aquecimento/volta à calma da zona.

    A rampa vai do piso da zona até o MESMO valor do bloco fixo — nunca acima.
    Se ela subisse até o topo da zona, um treino de uma zona só (recuperação, toda
    em Z1) sairia com as pontas mais fortes que o miolo: pico, queda, pico.
    """
    lo, _ = faixa_util_pct(zona or 0)
    return lo, _mid_pct(zona)


def build_zwo_xml(
    tipo: str,
    duracao_min: int,
    *,
    nome: str | None = None,
    descricao: str | None = None,
    autor: str = "IA Performance",
    antecipacao_s: int = ANTECIPACAO_PADRAO_S,
) -> str | None:
    """Monta o .zwo (Zwift Workout) do treino. Retorna a string XML, ou None se o
    tipo não tiver estrutura. Potências relativas ao FTP — não exige FTP salvo."""
    dados = preview_estrutura(tipo, duracao_min)
    if dados is None:
        return None

    segmentos = dados["segments"]
    nome = nome or tipo.replace("_", " ").title()
    descricao = descricao or _DESCRICOES.get(tipo, "Treino estruturado indoor.")

    blocos: list[str] = []
    total = len(segmentos)
    for i, seg in enumerate(segmentos):
        fase = seg["fase"]
        zona = seg["zona"]
        dur = int(seg["duracao_s"] or 0)

        # ── eventos de texto do bloco ───────────────────────────────────────────
        eventos: list[str] = []
        # Início: anuncia o esforço quando é intenso (o atleta vê "VAI!").
        if fase == "interval" and (zona or 0) >= 4:
            eventos.append(
                f'      <textevent timeoffset="1" message={quoteattr(_rotulo(fase, zona) + "!")}/>'
            )
        # Antecipação: no fim deste bloco, anuncia o próximo.
        if i + 1 < total:
            prox = segmentos[i + 1]
            rot = _rotulo(prox["fase"], prox["zona"])
            pdur = int(prox["duracao_s"] or 0)
            if prox["fase"] in ("warmup", "cooldown"):
                msg = f"Em {antecipacao_s}s: {rot} ({_fmt_dur(pdur)})."
            else:
                msg = f"Em {antecipacao_s}s: {rot} — {_fmt_dur(pdur)} a {round(_mid_pct(prox['zona']) * 100)}% FTP."
            off = max(0, dur - antecipacao_s)
            eventos.append(f'      <textevent timeoffset="{off}" message={quoteattr(msg)}/>')
        else:
            # Último bloco: parabeniza perto do fim.
            eventos.append(
                f'      <textevent timeoffset="{max(0, dur - 5)}" message="Treino concluído. Parabéns!"/>'
            )
        ev_xml = ("\n" + "\n".join(eventos) + "\n    ") if eventos else ""

        # ── elemento do bloco ───────────────────────────────────────────────────
        if fase == "warmup":
            piso, alvo = _ramp_pct(zona)
            blocos.append(f'    <Warmup Duration="{dur}" PowerLow="{_num(piso)}" PowerHigh="{_num(alvo)}">{ev_xml}</Warmup>')
        elif fase == "cooldown":
            # Zwift/MyWhoosh leem PowerLow como o INÍCIO da rampa: na volta à calma
            # o valor MAIOR vem primeiro, senão o app faz o treino subir no fim.
            piso, alvo = _ramp_pct(zona)
            blocos.append(f'    <Cooldown Duration="{dur}" PowerLow="{_num(alvo)}" PowerHigh="{_num(piso)}">{ev_xml}</Cooldown>')
        else:
            p = _num(_mid_pct(zona))
            blocos.append(f'    <SteadyState Duration="{dur}" Power="{p}">{ev_xml}</SteadyState>')

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<workout_file>\n'
        f'  <author>{escape(autor)}</author>\n'
        f'  <name>{escape(nome)}</name>\n'
        f'  <description>{escape(descricao)}</description>\n'
        '  <sportType>bike</sportType>\n'
        '  <tags>\n'
        f'    <tag name={quoteattr(tipo)}/>\n'
        '  </tags>\n'
        '  <workout>\n'
        + "\n".join(blocos)
        + '\n  </workout>\n'
        '</workout_file>\n'
    )
