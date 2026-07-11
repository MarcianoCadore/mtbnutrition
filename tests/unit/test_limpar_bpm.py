"""Limpeza de bpm/watts em descrições já gravadas (scripts/limpar_bpm_descricoes)."""
from scripts.limpar_bpm_descricoes import limpar_descricao as L


class TestLimparDescricao:
    def test_caso_do_ale(self):
        s = ("Seu treino mais longo da semana: 90 minutos contínuos pedalando na "
             "Zona 2 (113-132 bpm), num ritmo conversacional. Cadência 75-85 rpm.")
        out = L(s)
        assert "bpm" not in out
        assert "113-132" not in out
        assert "75-85 rpm" in out           # cadência preservada
        assert "Zona 2," in out             # frase intacta

    def test_parenteses_bpm(self):
        assert L("Base aeróbica em Z2 (146-158 bpm). Cadência 85-95 rpm.") == \
            "Base aeróbica em Z2. Cadência 85-95 rpm."

    def test_bpm_com_maior_menor(self):
        assert L("8x30s em Z5 (>177 bpm) com recuperação Z1.") == \
            "8x30s em Z5 com recuperação Z1."

    def test_parenteses_watts(self):
        assert L("Bloco em Z2 (171-231W). Cadência 85-95 rpm.") == \
            "Bloco em Z2. Cadência 85-95 rpm."

    def test_nao_remove_cadencia_rpm(self):
        assert "50-60 rpm" in L("4x6 min Z3 cadência baixa 50-60 rpm.")

    def test_idempotente(self):
        s = "Base aeróbica em Z2 (146-158 bpm). Cadência 85-95 rpm."
        assert L(L(s)) == L(s)

    def test_sem_bpm_inalterado(self):
        s = "90 min base aeróbica Z2. Cadência 85-95 rpm, ritmo conversacional."
        assert L(s) == s

    def test_none_e_vazio(self):
        assert L(None) is None
        assert L("") == ""
