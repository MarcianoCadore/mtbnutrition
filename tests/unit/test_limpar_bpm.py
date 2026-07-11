"""Limpeza conservadora de bpm em descrições já gravadas.

Remove apenas os PARÊNTESES de bpm (info suplementar) — nunca deixa rótulo
pendurado, nunca remove watts corretos por atleta, nunca toca em cadência.
"""
from scripts.limpar_bpm_descricoes import limpar_descricao as L


class TestLimparDescricao:
    def test_caso_do_ale(self):
        s = ("Seu treino mais longo da semana: 90 minutos contínuos pedalando na "
             "Zona 2 (113-132 bpm), num ritmo conversacional. Cadência 75-85 rpm.")
        out = L(s)
        assert "bpm" not in out and "113-132" not in out
        assert "75-85 rpm" in out            # cadência preservada
        assert "Zona 2, num ritmo" in out    # frase intacta, sem espaço antes da vírgula

    def test_parenteses_bpm_simples(self):
        assert L("Base aeróbica em Z2 (146-158 bpm). Cadência 85-95 rpm.") == \
            "Base aeróbica em Z2. Cadência 85-95 rpm."

    def test_bpm_com_maior_menor(self):
        assert L("8x30s em Z5 (>177 bpm) com recuperação Z1.") == \
            "8x30s em Z5 com recuperação Z1."

    def test_paren_bpm_com_texto_extra(self):
        assert L("60 min Z1 (109-139 bpm, idealmente <130). Leve.") == \
            "60 min Z1. Leve."

    def test_zona_antes_do_bpm_preserva_zona(self):
        assert L("- FC alvo: Z3–Z4 (148–165 bpm)") == "- FC alvo: Z3–Z4"

    def test_watts_em_parenteses_e_preservado(self):
        # Watts costumam ser as faixas reais (derivadas do FTP) — não remover.
        s = "2x12 min Sweet Spot (88–93% FTP = 213–225W):"
        assert L(s) == s

    def test_nao_remove_cadencia_rpm(self):
        assert "50-60 rpm" in L("4x6 min Z3 cadência baixa 50-60 rpm.")

    def test_bpm_solto_sem_parenteses_nao_e_tocado(self):
        # Conservador: fora de parênteses não mexe (evita rótulo pendurado tipo "FC alvo:").
        s = "- FC alvo: 142–149bpm"
        assert L(s) == s

    def test_idempotente(self):
        s = "Base aeróbica em Z2 (146-158 bpm). Cadência 85-95 rpm."
        assert L(L(s)) == L(s)

    def test_sem_bpm_inalterado(self):
        s = "90 min base aeróbica Z2. Cadência 85-95 rpm, ritmo conversacional."
        assert L(s) == s

    def test_none_e_vazio(self):
        assert L(None) is None
        assert L("") == ""
