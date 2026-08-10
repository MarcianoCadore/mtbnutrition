"""Duração planejada × duração enviada ao Garmin.

Regressão do bug do round-trip: os builders de treino intervalado recebiam
`duracao_min` e ignoravam, montando sempre a estrutura fixa do molde. O push
mandava `estimatedDurationInSecs` do molde (TEMPO=70min, VO2MAX=62min) e o pull
seguinte (garmin_service.sync_treinos_planejados) lia esse campo de volta e
regravava `duracao_min` no banco — o atleta salvava 110 min, clicava em
"Enviar + Sincronizar Garmin" e o plano voltava sozinho pros 70 min do molde.

Enquanto `total == duracao_min * 60` valer para todo tipo, o round-trip é
idempotente e o plano não pode ser revertido pelo sync.
"""
import pytest

from app.services.garmin_workout_service import (
    _BUILDERS,
    build_cycling_workout,
    preview_estrutura,
)

TIPOS = list(_BUILDERS)
# Abaixo de ~42 min o protocolo fixo do teste de FTP (20 min de teste +
# acelerações + pontas mínimas) não cabe — é o único piso legítimo.
PISO_TESTE_FTP = 42


@pytest.mark.parametrize("tipo", TIPOS)
@pytest.mark.parametrize("dur", [45, 60, 62, 70, 80, 95, 110, 150, 210, 300])
def test_workout_enviado_tem_a_duracao_planejada(tipo, dur):
    if tipo == "TESTE_FTP" and dur < PISO_TESTE_FTP:
        pytest.skip("protocolo fixo do teste de FTP não cabe abaixo do piso")
    w = build_cycling_workout(tipo, dur, "x")
    assert w.estimatedDurationInSecs == dur * 60, (
        f"{tipo} {dur}min foi pro Garmin com {w.estimatedDurationInSecs // 60}min — "
        "o pull vai regravar essa duração no banco"
    )


@pytest.mark.parametrize("tipo", TIPOS)
def test_nenhuma_duracao_realista_diverge(tipo):
    piso = PISO_TESTE_FTP if tipo == "TESTE_FTP" else 25
    divergentes = [d for d in range(piso, 301) if _BUILDERS[tipo](d)[1] != d * 60]
    assert not divergentes, f"{tipo} diverge em {divergentes[:5]}"


@pytest.mark.parametrize("tipo,dur,molde", [("TEMPO", 110, 70), ("VO2MAX", 95, 62)])
def test_regressao_semana_nao_volta_pro_molde(tipo, dur, molde):
    """O caso reportado: TEMPO 110min virava 70min e VO2Max 95min virava 62min."""
    assert build_cycling_workout(tipo, dur, "x").estimatedDurationInSecs // 60 not in (molde,)
    assert build_cycling_workout(tipo, dur, "x").estimatedDurationInSecs // 60 == dur


@pytest.mark.parametrize("tipo", TIPOS)
@pytest.mark.parametrize("dur", [60, 95, 150])
def test_soma_dos_segmentos_bate_com_o_total(tipo, dur):
    """O gráfico do portal, o .zwo e o ERG saem de preview_estrutura — se a soma
    dos segmentos não fechar com o total, os três divergem do treino real."""
    dados = preview_estrutura(tipo, dur)
    assert sum(s["duracao_s"] for s in dados["segments"]) == dados["total_s"]


@pytest.mark.parametrize("tipo", ["TEMPO", "FORCA", "TIROS", "VO2MAX"])
def test_intervalado_ganha_series_com_mais_tempo(tipo):
    """Tempo a mais vira mais série (até o teto do tipo), não um bloco esticado."""
    def series(dur):
        segs = preview_estrutura(tipo, dur)["segments"]
        return sum(1 for s in segs if s["fase"] == "interval" and s["zona"] in (3, 5))

    assert series(120) > series(60)


@pytest.mark.parametrize("tipo", ["TEMPO", "FORCA", "TIROS", "VO2MAX"])
def test_treino_longo_nao_vira_so_intervalo(tipo):
    """Acima do teto de séries o excedente vira rodagem Z2 — uma sessão de 4h não
    pode ser toda em Z3/Z5."""
    segs = preview_estrutura(tipo, 240)["segments"]
    forte_s = sum(s["duracao_s"] for s in segs if s["zona"] in (3, 5))
    assert forte_s < 240 * 60 * 0.6, f"{tipo}: {forte_s / 60:.0f}min de esforço forte em 240min"


@pytest.mark.parametrize("tipo", TIPOS)
@pytest.mark.parametrize("dur", [45, 95, 210])
def test_sempre_tem_aquecimento_e_volta_a_calma(tipo, dur):
    if tipo == "TESTE_FTP" and dur < PISO_TESTE_FTP:
        pytest.skip("protocolo fixo do teste de FTP não cabe abaixo do piso")
    segs = preview_estrutura(tipo, dur)["segments"]
    assert segs[0]["fase"] == "warmup" and segs[0]["duracao_s"] >= 300
    assert segs[-1]["fase"] == "cooldown" and segs[-1]["duracao_s"] >= 300


@pytest.mark.parametrize("dur", [45, 60, 90, 120])
def test_teste_ftp_mantem_o_bloco_de_20min(dur):
    """A duração muda as pontas; o esforço de 20 min que dá o número é intocável."""
    segs = preview_estrutura("TESTE_FTP", dur)["segments"]
    assert any(s["duracao_s"] == 1200 and s["zona"] == 4 for s in segs)
