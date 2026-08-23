"""Rótulo de tipo que abre a descrição ("Tiros — 75 min...").

Caso reportado em 2026-08-23: o card de segunda mostrava o badge "VO2Max" (a
série principal tem "5×2 min em Z4/Z5" — minutos em Z5 → VO2máx, via
ai_service.tipo_definitivo) enquanto as Notas do treino abriam com "Tiros — ",
o nome que a IA escreveu no texto. Dois nomes para o mesmo treino confundem: o
badge é a fonte única do tipo, então o rótulo sai do texto.
"""
from app.services.plano_semana_service import (
    limpar_rotulo_tipo_descricao as L,
    limpar_descricao_planejada as C,
)


class TestLimparRotuloTipo:
    def test_caso_reportado_tiros_com_badge_vo2max(self):
        s = (
            "Tiros — 75 min. 15 min aquecimento progressivo Z1→Z2. "
            "Sessão principal: 8×30 seg all-out + 30 seg recuperação passiva. "
            "5×2 min em Z4/Z5 com 2 min de recuperação Z1 entre cada. "
            "15 min volta à calma Z1."
        )
        out = L(s)
        assert not out.startswith("Tiros")
        assert out.startswith("75 min.")
        # a prescrição inteira continua lá — some só o rótulo
        assert "8×30 seg all-out" in out
        assert "5×2 min em Z4/Z5" in out

    def test_rotulo_nao_muda_a_classificacao(self):
        # tipo_definitivo lê a ESTRUTURA da série principal, não o rótulo:
        # tirar o "Tiros —" não pode virar o badge.
        from app.services.ai_service import tipo_definitivo
        s = ("Tiros — 75 min. 8×30 seg all-out. "
             "5×2 min em Z4/Z5 com 2 min de recuperação Z1 entre cada.")
        assert tipo_definitivo(s) == "VO2MAX"
        assert tipo_definitivo(L(s)) == "VO2MAX"

    def test_separadores(self):
        assert L("VO2Max — 4x4 min Z5.") == "4x4 min Z5."
        assert L("Z2 Longo – 3h de base aeróbica.") == "3h de base aeróbica."
        assert L("Tempo: 3×10 min em Z4.") == "3×10 min em Z4."
        assert L("Força (bike) - 6×5 min sobremarcha.") == "6×5 min sobremarcha."

    def test_vocabulario_de_tipos(self):
        assert L("Teste FTP — 20 min all-out.") == "20 min all-out."
        assert L("Recuperação — pedal leve em Z1.") == "Pedal leve em Z1."
        assert L("Z2 — 90 min contínuos.") == "90 min contínuos."
        assert L("Longão — 4h no ritmo do dia.") == "4h no ritmo do dia."

    def test_primeira_letra_do_corpo_sobe_para_maiuscula(self):
        assert L("Recuperação — pedal leve.") == "Pedal leve."

    def test_academia_intacta(self):
        # "ACADEMIA — Força MTB (foco: …)" é a primeira linha do formato
        # obrigatório; extrair_exercicios_academia conta com ela.
        s = ("ACADEMIA — Força MTB (foco: pernas+core)\n\n"
             "POR QUE HOJE: base.\n\nEXERCÍCIOS:\n1. Agachamento — 3x10 — 40 kg")
        assert L(s) == s

    def test_prosa_com_travessao_intacta(self):
        for s in (
            "Atenção — hidrate bem antes do treino.",
            "Tempo-limite de 90 min para o percurso.",
            "Recuperação de 4 min Z1-Z2 entre cada bloco — desça completamente.",
            "🎯 Alvo — Outdoor (FC): Zona 2 142-149 bpm",
            "15 min aquecimento. 5×4 min Z5.",
        ):
            assert L(s) == s

    def test_sem_rotulo_nao_capitaliza(self):
        # A maiúscula é consequência da remoção do rótulo; sem remoção o texto
        # sai byte a byte igual ao que entrou.
        for s in ("x" * 300, "pedal leve em Z1, cadência alta.", "8x30s all-out."):
            assert L(s) == s

    def test_idempotente(self):
        s = "Tiros — 75 min. 8×30 seg all-out."
        assert L(L(s)) == L(s) == "75 min. 8×30 seg all-out."

    def test_none_e_vazio(self):
        assert L(None) is None
        assert L("") == ""

    def test_pipeline_completo(self):
        # cabeçalho do round-trip sai primeiro; só então o rótulo é procurado na
        # primeira linha da prescrição. Legenda de alvos preservada.
        s = (
            "VO2MAX — 2026-08-24\n"
            "Tiros — 75 min. 5×2 min em Z4/Z5 (177-192 bpm) com 2 min Z1.\n\n"
            "🎯 Alvo — Outdoor (FC): Zona 5 177-192 bpm"
        )
        out = C(s)
        assert out.startswith("75 min.")
        assert "VO2MAX — 2026-08-24" not in out
        assert "bpm)" not in out          # parêntese de bpm removido
        assert "🎯 Alvo — Outdoor (FC): Zona 5 177-192 bpm" in out
