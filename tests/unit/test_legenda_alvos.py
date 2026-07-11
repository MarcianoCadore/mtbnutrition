"""Legenda de alvos (FC + watts) anexada às descrições de treino.

Contexto (bug do Alderossi): a descrição gerada pela IA dizia "Zona 2 (113-132
bpm)" quando a Z2 real dele é 132-150 — a IA transcrevia bpm errado em texto
livre. Correção: a IA passa a citar só o nome da zona e o CÓDIGO anexa as faixas
reais do atleta (nunca fixas), em FC (outdoor) e watts (indoor).

Requisitos travados aqui:
- números vêm das zonas de CADA usuário, nunca hardcoded;
- Alderossi: Z2 = 132-150 (e não 113-132);
- cobre FC e watts;
- a legenda NÃO altera a classificação do treino (usa "Zona N", não "ZN").
"""
import app.services.plano_semana_service as p
from app.services.ai_service import classificar_por_texto

# Zonas reais do Alderossi (FC)
FC_ALDEROSSI = [
    {"zona": 1, "min": 113, "max": 131},
    {"zona": 2, "min": 132, "max": 150},
    {"zona": 3, "min": 151, "max": 163},
    {"zona": 4, "min": 164, "max": 175},
    {"zona": 5, "min": 176, "max": 189},
]
# Zonas de outro atleta (frequências diferentes) — prova que não é fixo
FC_OUTRO = [
    {"zona": 1, "min": 120, "max": 141},
    {"zona": 2, "min": 142, "max": 154},
    {"zona": 3, "min": 155, "max": 161},
    {"zona": 4, "min": 162, "max": 172},
    {"zona": 5, "min": 173, "max": 185},
]
WATTS = [
    {"zona": 1, "min": 0, "max": 165},
    {"zona": 2, "min": 168, "max": 225},
    {"zona": 3, "min": 228, "max": 270},
    {"zona": 4, "min": 273, "max": 315},
    {"zona": 5, "min": 318, "max": 360},
    {"zona": 6, "min": 363, "max": 450},
    {"zona": 7, "min": 453, "max": 9999},
]


class TestLegenda:
    def test_alderossi_z2_correta(self):
        leg = p._legenda_alvos(FC_ALDEROSSI, None)
        assert "Zona 2 132-150" in leg
        assert "113-132" not in leg  # o número errado do bug não aparece

    def test_numeros_sao_por_usuario_nao_fixos(self):
        a = p._legenda_alvos(FC_ALDEROSSI, None)
        b = p._legenda_alvos(FC_OUTRO, None)
        assert a != b
        assert "132-150" in a and "142-154" in b

    def test_cobre_fc_e_watts(self):
        leg = p._legenda_alvos(FC_ALDEROSSI, WATTS)
        assert "Outdoor (FC)" in leg and "bpm" in leg
        assert "Indoor (Watts)" in leg and "W" in leg
        assert "Zona 2 168-225" in leg  # watts Z2

    def test_watts_ausente_sem_ftp(self):
        leg = p._legenda_alvos(FC_ALDEROSSI, None)
        assert "Watts" not in leg

    def test_sem_zonas_retorna_vazio(self):
        assert p._legenda_alvos([], None) == ""

    def test_fmt_faixa_bordas(self):
        assert p._fmt_faixa({"min": 132, "max": 150}) == "132-150"
        assert p._fmt_faixa({"min": 0, "max": 165}) == "<165"
        assert p._fmt_faixa({"min": 453, "max": 9999}) == ">453"


class TestAnexar:
    def test_anexa_em_bike_pula_descanso_e_academia(self):
        treinos = [
            {"tipo": "Z2_LONGO", "descricao": "90 min base Z2."},
            {"tipo": "DESCANSO", "descricao": ""},
            {"tipo": "ACADEMIA", "descricao": "agachamento 4x8"},
        ]
        p._anexar_legenda_alvos(treinos, FC_ALDEROSSI, WATTS)
        assert "Outdoor (FC)" in treinos[0]["descricao"]
        assert treinos[1]["descricao"] == ""
        assert treinos[2]["descricao"] == "agachamento 4x8"

    def test_idempotente(self):
        treinos = [{"tipo": "TEMPO", "descricao": "3x10 Z3."}]
        p._anexar_legenda_alvos(treinos, FC_ALDEROSSI, None)
        p._anexar_legenda_alvos(treinos, FC_ALDEROSSI, None)
        assert treinos[0]["descricao"].count("Outdoor (FC)") == 1


class TestClassificacaoNaoQuebra:
    """A legenda não pode mudar o tipo classificado do treino."""

    CASOS = [
        ("10×30s sprint máximo Z5, cadência 100-115 rpm. Recuperação Z1.", "TIROS"),
        ("90 min base aeróbica Z2, cadência 85-95 rpm, ritmo conversacional.", "Z2_LONGO"),
        ("75 min recuperação ativa Z1. Sem esforço.", "RECUPERACAO"),
        ("15 min aquecimento. 3×15 min Z3-Z4, recuperação Z2. Cadência 88-95 rpm.", "TEMPO"),
    ]

    def test_tipo_estavel_com_legenda(self):
        for desc, _ in self.CASOS:
            antes = classificar_por_texto(desc)
            treinos = [{"tipo": antes or "Z2_LONGO", "descricao": desc}]
            p._anexar_legenda_alvos(treinos, FC_ALDEROSSI, WATTS)
            depois = classificar_por_texto(treinos[0]["descricao"])
            assert depois == antes, (
                f"legenda mudou classificação: {antes} → {depois} em {desc!r}"
            )
