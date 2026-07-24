"""tss_planejado (wrapper público de _tss_esperado) — TSS estimado de um
treino planejado, usado para a linha "P: ... TSS" do card no calendário."""
from app.services.garmin_service import tss_planejado


class TestTssPlanejado:
    def test_z2_longo_tem_tss(self):
        assert tss_planejado("Z2_LONGO", 120) == round(2 * 0.65 ** 2 * 100)

    def test_sem_duracao_none(self):
        assert tss_planejado("Z2_LONGO", None) is None

    def test_academia_sem_fator_definido_none(self):
        assert tss_planejado("ACADEMIA", 60) is None

    def test_descanso_none(self):
        assert tss_planejado("DESCANSO", None) is None

    def test_teste_ftp_none(self):
        assert tss_planejado("TESTE_FTP", 62) is None
