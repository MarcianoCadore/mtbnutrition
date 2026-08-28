"""O treino desenhado/exportado é o que a DESCRIÇÃO prescreve.

Bug de origem: o card dizia "3×15 min em Z3/Z4 com 5 min de recuperação" e o
gráfico do portal desenhava 5 blocos de 10 min — o molde fixo do tipo (TEMPO) era
a única fonte da estrutura, e o desenho contradizia o texto logo abaixo dele.
"""
import pytest

from app.services.garmin_workout_service import (
    build_cycling_workout,
    preview_estrutura,
)
from app.services.prescricao_service import parse_prescricao

# A descrição do print do atleta, com a linha de alvos que o app anexa.
DESC_TEMPO = (
    "Treino de limiar — 100 min. 15 min aquecimento progressivo Z1→Z2. "
    "Sessão principal: 3×15 min em Z3/Z4 com 5 min de recuperação Z1 entre cada bloco. "
    "15 min volta à calma Z1."
)
LEGENDA = "\n\n🎯 Alvo — Outdoor (FC): Zona 1 100-120 · Zona 2 120-140 · Zona 3 140-155 bpm"


def _blocos(segs):
    """Blocos de esforço (o que o atleta conta como 'série')."""
    return [s for s in segs if s["fase"] == "interval" and s["zona"] and s["zona"] >= 3]


class TestLeituraDoTexto:
    @pytest.mark.parametrize("texto,series,esforco_s,recup_s", [
        (DESC_TEMPO, 3, 900, 300),
        ("15 min aquecimento Z1-Z2. 3×15 min Z3-Z4, recuperação 5 min Z2 entre blocos. "
         "10 min volta à calma Z1.", 3, 900, 300),
        ("20 min aquecimento progressivo. 10×30s sprint máximo Z5, cadência 100-115 rpm. "
         "Recuperação 3.5 min Z1 entre cada. 15 min volta à calma.", 10, 30, 210),
        ("15 min aquecimento. 6×8 min cadência 50-58 rpm marcha pesada Z3. "
         "Recuperação 3 min Z1. 10 min volta à calma.", 6, 480, 180),
        ("4 blocos de 12 min em Z4 com 6 min de recuperação Z2.", 4, 720, 360),
    ])
    def test_le_a_serie_principal(self, texto, series, esforco_s, recup_s):
        p = parse_prescricao(texto)
        assert (p["series"], p["esforco_s"], p["recuperacao_s"]) == (series, esforco_s, recup_s)

    def test_zonas_do_texto(self):
        p = parse_prescricao(DESC_TEMPO)
        # "Z3/Z4" → vale o piso prescrito; a recuperação é a zona citada DEPOIS do
        # "5 min", não a do esforço, que vem antes na mesma frase.
        assert p["zona_esforco"] == 3
        assert p["zona_recuperacao"] == 1
        assert (p["aquecimento_s"], p["zona_aquecimento"]) == (900, 1)
        assert (p["volta_calma_s"], p["zona_volta_calma"]) == (900, 1)

    def test_legenda_de_alvos_nao_e_prescricao(self):
        """A legenda ("Zona 3 140-155 bpm") não pode virar série nem trocar zona."""
        assert parse_prescricao(DESC_TEMPO + LEGENDA) == parse_prescricao(DESC_TEMPO)

    def test_recuperacao_sem_numero_fica_none(self):
        """"3x10 min Z3, recuperação Z2" não diz de quanto é a recuperação — o
        molde do tipo é que completa (o "10 min" do bloco não pode virar ela)."""
        assert parse_prescricao("3x10 min Z3, recuperação Z2.")["recuperacao_s"] is None

    @pytest.mark.parametrize("texto", [
        None, "", "   ",
        "Base aeróbica em Z2. Cadência: 85-95 rpm. Esforço controlado.",
        "Pedal leve em Z1. Recuperação ativa, esforço mínimo.",
    ])
    def test_sem_serie_no_texto_volta_none(self, texto):
        assert parse_prescricao(texto) is None

    def test_serie_dominante_vence_a_secundaria(self):
        p = parse_prescricao("15 min aquecimento. 4×8 min Z4 com 4 min de recuperação Z2. "
                             "No fim, 3×20s de acelerações. 10 min volta à calma.")
        assert (p["series"], p["esforco_s"]) == (4, 480)


class TestGraficoSegueADescricao:
    def test_tres_blocos_de_quinze(self):
        segs = preview_estrutura("TEMPO", 100, descricao=DESC_TEMPO)["segments"]
        blocos = _blocos(segs)
        assert len(blocos) == 3
        assert {b["duracao_s"] for b in blocos} == {900}

    def test_sem_descricao_continua_no_molde(self):
        """Quem não tem prescrição legível (import do Garmin, treino antigo) segue
        desenhando pelo molde do tipo."""
        assert len(_blocos(preview_estrutura("TEMPO", 100)["segments"])) == 5

    def test_pontas_e_recuperacao_do_texto(self):
        segs = preview_estrutura("TEMPO", 100, descricao=DESC_TEMPO)["segments"]
        assert segs[0]["fase"] == "warmup" and segs[0]["duracao_s"] == 900
        assert segs[-1]["fase"] == "cooldown" and segs[-1]["duracao_s"] == 900
        assert {s["duracao_s"] for s in segs if s["fase"] == "recovery"} == {300}

    @pytest.mark.parametrize("dur", [60, 75, 90, 100, 120, 180])
    def test_soma_sempre_fecha_com_a_duracao_do_dia(self, dur):
        """Invariante do round-trip com o Garmin: total == duracao_min × 60,
        senão o pull seguinte regrava a duração do plano."""
        dados = preview_estrutura("TEMPO", dur, descricao=DESC_TEMPO)
        assert sum(s["duracao_s"] for s in dados["segments"]) == dados["total_s"] == dur * 60

    def test_serie_que_nao_cabe_no_dia_e_cortada_pelo_tempo(self):
        """Descrição maior que a duração planejada: os blocos que couberem, com o
        tamanho descrito — nunca estourando o tempo do dia."""
        segs = preview_estrutura("TEMPO", 60, descricao=DESC_TEMPO)["segments"]
        assert len(_blocos(segs)) < 3
        assert sum(s["duracao_s"] for s in segs) == 60 * 60

    def test_teste_ftp_mantem_o_protocolo(self):
        """O TESTE_FTP é protocolo fixo e sua descrição cita "3×(30s Z5 + 1min Z1)"
        no aquecimento — isso não pode virar a sessão principal."""
        desc = ("TESTE FTP (20min): esforço máximo sustentável. Aquecimento: 10min Z1 → "
                "5min Z3 progressivo → 3×(30s Z5 + 1min Z1) → 2min Z1. Desaquecimento: 15min Z1.")
        segs = preview_estrutura("TESTE_FTP", 57, descricao=desc)["segments"]
        assert any(s["duracao_s"] == 1200 and s["zona"] == 4 for s in segs), "teste de 20 min sumiu"

    @pytest.mark.parametrize("tipo", ["Z2_LONGO", "RECUPERACAO"])
    def test_continuos_nao_viram_intervalado(self, tipo):
        segs = preview_estrutura(tipo, 120, descricao=DESC_TEMPO)["segments"]
        assert len(segs) == 3, "treino contínuo não segue série descrita para outro tipo"


class TestRelogioEArquivoBatemComOGrafico:
    def test_workout_do_garmin_usa_a_mesma_estrutura(self):
        w = build_cycling_workout("TEMPO", 100, "x", DESC_TEMPO)
        grupo = next(s for s in w.workoutSegments[0].workoutSteps
                     if getattr(s, "workoutSteps", None))
        assert grupo.numberOfIterations == 3
        assert w.estimatedDurationInSecs == 100 * 60

    def test_zwo_exporta_os_blocos_descritos(self):
        import xml.etree.ElementTree as ET
        from app.services.zwo_service import build_zwo_xml

        xml = build_zwo_xml("TEMPO", 100, nome="Tempo", descricao=DESC_TEMPO)
        blocos = ET.fromstring(xml).find("workout").findall("SteadyState")
        assert sum(1 for b in blocos if b.get("Duration") == "900") == 3
