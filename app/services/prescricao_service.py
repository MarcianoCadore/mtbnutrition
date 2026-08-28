"""Leitura da PRESCRIÇÃO escrita na descrição do treino.

A descrição é a fonte da verdade do que o atleta vai fazer — é o texto que ele lê
no card ("3×15 min em Z3/Z4 com 5 min de recuperação Z1 entre cada bloco"). O
gráfico do portal, o .zwo e o workout enviado ao Garmin saíam só do molde fixo do
tipo (TEMPO = blocos de 10 min), então um treino descrito com 3 blocos de 15 min
era desenhado com 5 blocos de 10 — o desenho contradizia o texto logo abaixo dele.

Aqui os números da série principal (quantos blocos, de quanto tempo, em que zona,
com quanta recuperação) e das pontas (aquecimento e volta à calma) saem do texto.
O que o texto NÃO disser volta None, e quem chama completa com o molde do tipo
(garmin_workout_service._MOLDES_INTERVALADO) — nunca se chuta um número.

Faixa de zona ("Z3/Z4", "Z1→Z2"): vale a PRIMEIRA zona citada. O relógio aceita
uma faixa só por step e o piso é o que o atleta precisa segurar; é também o que os
moldes já mandavam, então ler a descrição muda a ESTRUTURA do treino sem mexer no
alvo que o aparelho vinha alertando.
"""

import re

# Unidades como a IA escreve: "15 min", "15min", "15 minutos", "30s", "30 seg".
_MIN = r"min(?:\.|utos?)?"
_SEG = r"s(?:eg(?:\.|undos?)?)?"
_NUM = r"\d+(?:[.,]\d+)?"
_UNID = rf"(?P<unid>{_MIN}|{_SEG})"

# Série principal. Duas escritas cobrem o que aparece nas descrições:
#   "3×15 min", "10x30s", "3 × (15 min + 5 min)"   →  N × duração
#   "3 blocos de 15 min", "8 tiros de 30s"          →  N blocos de duração
_SERIE_RES = (
    re.compile(rf"(?P<n>\d{{1,2}})\s*[x×]\s*\(?\s*(?P<dur>{_NUM})\s*{_UNID}\b", re.IGNORECASE),
    re.compile(
        rf"(?P<n>\d{{1,2}})\s*(?:blocos?|s[ée]ries?|tiros?|sprints?|intervalos?|"
        rf"repeti[çc][õo]es|reps?)\s*(?:de\s*)?(?P<dur>{_NUM})\s*{_UNID}\b",
        re.IGNORECASE,
    ),
)

# "Z3", "Z 4", "Z3/Z4". NÃO casa "Zona 3" — é assim que a legenda de alvos
# (plano_semana_service._legenda_alvos) escreve as faixas de bpm/watts do atleta,
# e ela não pode ser lida como prescrição.
_ZONA_RE = re.compile(r"\bz\s*([1-5])\b", re.IGNORECASE)

_REC_PALAVRA = r"recupera\w*|recup\.?|soltura|descanso|entre\s+(?:cada|os|as)?\s*(?:blocos?|s[ée]ries?|tiros?)"
# "5 min de recuperação Z1" (número antes) e "Recuperação 3.5 min Z1" (depois).
_REC_RES = (
    re.compile(rf"({_NUM})\s*{_UNID}\b[^.\n]{{0,25}}?(?:{_REC_PALAVRA})", re.IGNORECASE),
    re.compile(rf"(?:{_REC_PALAVRA})[^.\n]{{0,25}}?({_NUM})\s*{_UNID}\b", re.IGNORECASE),
)

_AQUECIMENTO = r"aquecimento|aquecer|aquecendo"
_VOLTA_CALMA = r"volta\s*[àa]\s*calma|volta-calma|desaquecimento|desaquecer|soltura\s+final"

# Marcadores da legenda de alvos anexada pelo app: dali pra baixo é tabela de
# bpm/watts, não prescrição.
_FIM_DA_PRESCRICAO = re.compile(r"^\s*(?:🎯|⚡)", re.MULTILINE)

# Limites de sanidade — fora disto o texto não estava descrevendo uma série.
_SERIES_MIN, _SERIES_MAX = 2, 30
_ESFORCO_MIN_S, _ESFORCO_MAX_S = 10, 45 * 60
_RECUP_MIN_S, _RECUP_MAX_S = 10, 30 * 60
_PONTA_MIN_S, _PONTA_MAX_S = 60, 60 * 60


def _segundos(valor: str, unidade: str) -> int:
    n = float(valor.replace(",", "."))
    return round(n * 60) if unidade.lower().startswith("m") else round(n)


def _frases(texto: str) -> list[str]:
    """Quebra em frases. O ponto de "3.5 min" não separa nada — só o ponto que
    não é seguido de dígito."""
    return [f for f in re.split(r"(?:\.(?!\d)|[;\n])", texto) if f.strip()]


def _zonas(trecho: str) -> list[int]:
    return [int(m.group(1)) for m in _ZONA_RE.finditer(trecho)]


def _primeira_zona(trecho: str) -> int | None:
    z = _zonas(trecho)
    return z[0] if z else None


def _ponta(frases: list[str], palavras: str) -> tuple[int | None, int | None]:
    """(duração, zona) do aquecimento ou da volta à calma, procurados nos dois
    sentidos: "15 min aquecimento" e "Aquecimento: 10 min"."""
    antes = re.compile(rf"({_NUM})\s*{_UNID}\b[^.\n]{{0,25}}?(?:{palavras})", re.IGNORECASE)
    depois = re.compile(rf"(?:{palavras})[^.\n]{{0,25}}?({_NUM})\s*{_UNID}\b", re.IGNORECASE)
    for frase in frases:
        for padrao in (antes, depois):
            m = padrao.search(frase)
            if not m:
                continue
            segundos = _segundos(m.group(1), m.group("unid"))
            if not (_PONTA_MIN_S <= segundos <= _PONTA_MAX_S):
                continue
            return segundos, _primeira_zona(frase)
    return None, None


def _recuperacao(frases: list[str], i_serie: int, resto_da_frase: str) -> tuple[int | None, int | None]:
    """(duração, zona) da recuperação entre os blocos: no que vem DEPOIS da série
    na mesma frase, ou na frase seguinte.

    Nunca na frase inteira: em "3x10 min Z3, recuperação Z2" (que não diz de
    quanto é a recuperação) o "10 min" do próprio bloco viraria a recuperação."""
    for trecho in (resto_da_frase, *frases[i_serie + 1:i_serie + 2]):
        for padrao in _REC_RES:
            m = padrao.search(trecho)
            if not m:
                continue
            segundos = _segundos(m.group(1), m.group("unid"))
            if not (_RECUP_MIN_S <= segundos <= _RECUP_MAX_S):
                continue
            # A zona da recuperação é a que vem LOGO DEPOIS do "5 min" ("5 min de
            # recuperação Z1"). Procurar na frase inteira pegaria a zona do
            # esforço, que costuma vir antes.
            return segundos, _primeira_zona(trecho[m.end("unid"):])
    return None, None


def parse_prescricao(descricao: str | None) -> dict | None:
    """Extrai a estrutura descrita no texto.

    Retorna None quando o texto não traz uma série principal legível (treino
    contínuo, descrição vaga ou vazia) — aí o molde do tipo continua valendo.
    Campos ausentes voltam None: quem chama completa com o molde.
    """
    if not descricao or not descricao.strip():
        return None

    texto = _FIM_DA_PRESCRICAO.split(descricao)[0]
    frases = _frases(texto)

    # Série dominante: a que soma mais tempo de esforço. Descrições que citam uma
    # série secundária ("+ 3×20s de acelerações no fim") não podem virar o treino.
    melhor = None
    for i, frase in enumerate(frases):
        for padrao in _SERIE_RES:
            for m in padrao.finditer(frase):
                n = int(m.group("n"))
                esforco_s = _segundos(m.group("dur"), m.group("unid"))
                if not (_SERIES_MIN <= n <= _SERIES_MAX):
                    continue
                if not (_ESFORCO_MIN_S <= esforco_s <= _ESFORCO_MAX_S):
                    continue
                if melhor is None or n * esforco_s > melhor[0]:
                    melhor = (n * esforco_s, n, esforco_s, i, frase[m.end():])
    if melhor is None:
        return None

    _, series, esforco_s, i_serie, resto = melhor

    # Zona do esforço: a que aparece depois do "N×D min" e antes de se falar em
    # recuperação (senão a Z1 da recuperação viraria o alvo do bloco).
    corte = re.search(_REC_PALAVRA, resto, re.IGNORECASE)
    zona_esforco = _primeira_zona(resto[:corte.start()] if corte else resto)
    if zona_esforco is None:
        zona_esforco = _primeira_zona(frases[i_serie])

    recuperacao_s, zona_recuperacao = _recuperacao(frases, i_serie, resto)
    aquecimento_s, zona_aquecimento = _ponta(frases, _AQUECIMENTO)
    volta_calma_s, zona_volta_calma = _ponta(frases, _VOLTA_CALMA)

    return {
        "series": series,
        "esforco_s": esforco_s,
        "zona_esforco": zona_esforco,
        "recuperacao_s": recuperacao_s,
        "zona_recuperacao": zona_recuperacao,
        "aquecimento_s": aquecimento_s,
        "zona_aquecimento": zona_aquecimento,
        "volta_calma_s": volta_calma_s,
        "zona_volta_calma": zona_volta_calma,
    }
