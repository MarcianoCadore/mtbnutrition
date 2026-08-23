"""Formatação da semana que o chat lê (_linhas_treinos).

O contexto antigo achatava tudo numa linha por item do array: o sub-bloco de
academia de um dia de bike sumia, e um "extra" (origem="extra") aparecia como
se fosse o treino principal daquele dia. O chat então afirmava coisas que o
calendário não dizia.
"""
from app.services.chat_service import _linhas_treinos

SEG = "2026-06-22"
TER = "2026-06-23"


class TestAcademia:
    def test_sub_bloco_aparece_sob_o_treino_do_dia(self):
        linhas = _linhas_treinos([{
            "data": SEG, "tipo": "Z2_LONGO", "duracao_min": 90, "descricao": "Base Z2",
            "academia": {"duracao_min": 45, "descricao": "Core + posterior de coxa"},
        }])
        assert len(linhas) == 2
        assert "[Z2_LONGO]" in linhas[0]
        assert linhas[1].strip().startswith("+ ACADEMIA 45min no mesmo dia")
        assert "Core + posterior de coxa" in linhas[1]

    def test_sem_academia_nao_gera_linha(self):
        linhas = _linhas_treinos([
            {"data": SEG, "tipo": "TIROS", "duracao_min": 60, "descricao": "8x30s"},
        ])
        assert len(linhas) == 1

    def test_academia_sem_descricao_e_ignorada(self):
        linhas = _linhas_treinos([{
            "data": SEG, "tipo": "TIROS", "duracao_min": 60,
            "academia": {"duracao_min": 40},
        }])
        assert len(linhas) == 1


class TestExtras:
    def test_extra_marcado_e_depois_do_primario(self):
        # Extra listado ANTES do primário no array — a ordenação tem de corrigir.
        linhas = _linhas_treinos([
            {"data": SEG, "tipo": "ACADEMIA", "duracao_min": 50, "origem": "extra"},
            {"data": SEG, "tipo": "TIROS", "duracao_min": 60},
        ])
        assert "[TIROS] PLANEJADO" in linhas[0]
        assert "EXTRA" not in linhas[0]
        assert "[ACADEMIA] EXTRA PLANEJADO" in linhas[1]

    def test_ordena_por_data(self):
        linhas = _linhas_treinos([
            {"data": TER, "tipo": "TEMPO", "duracao_min": 70},
            {"data": SEG, "tipo": "TIROS", "duracao_min": 60},
        ])
        assert SEG in linhas[0] and TER in linhas[1]


class TestRealizado:
    def test_sessao_relatada_e_identificada(self):
        linhas = _linhas_treinos([{
            "data": SEG, "tipo": "ACADEMIA", "duracao_min": 40, "descricao": "Full body",
            "resultado": {
                "origem": "relato_atleta", "duracao_min": 40, "fc_invalida": True,
                "analise_ia": {"nota": 8},
            },
        }])
        assert "REALIZADO 40min" in linhas[0]
        assert "(nota 8)" in linhas[0]
        assert "relatado pelo atleta" in linhas[0]
        # Não confunde com o caso "tinha FC mas foi descartada".
        assert "[FC ignorada]" not in linhas[0]

    def test_fc_ignorada_de_dispositivo(self):
        linhas = _linhas_treinos([{
            "data": SEG, "tipo": "TIROS", "duracao_min": 60,
            "resultado": {"duracao_min": 62, "fc_invalida": True, "avg_power": 210},
        }])
        assert "[FC ignorada]" in linhas[0]

    def test_descanso(self):
        linhas = _linhas_treinos([{"data": SEG, "tipo": "DESCANSO"}])
        assert linhas[0].strip() == f"{SEG} DESCANSO"


class TestDescricao:
    def test_quebras_de_linha_viram_espaco(self):
        """A descrição é multi-linha; sem normalizar, uma entrada vira várias."""
        linhas = _linhas_treinos([{
            "data": SEG, "tipo": "VO2MAX", "duracao_min": 62,
            "descricao": "15 min aquecimento.\n5x4 min Z5.\n15 min volta à calma.",
        }])
        assert len(linhas) == 1
        assert "\n" not in linhas[0]

    def test_rotulo_de_tipo_nao_vai_pro_chat(self):
        # O badge do dia é VO2Max (5x2 min em Z4/Z5), mas a IA abriu a descrição
        # com "Tiros —". Se esse rótulo chegasse ao contexto, o chat repetiria o
        # nome errado pro atleta (caso reportado em 2026-08-23).
        linhas = _linhas_treinos([{
            "data": SEG, "tipo": "VO2MAX", "duracao_min": 75,
            "descricao": "Tiros — 75 min. 5x2 min em Z4/Z5 com 2 min Z1.",
        }], desc_max=200)
        assert "Tiros" not in linhas[0]
        assert "[VO2MAX]" in linhas[0]
        assert "5x2 min em Z4/Z5" in linhas[0]

    def test_truncada_no_limite(self):
        linhas = _linhas_treinos(
            [{"data": SEG, "tipo": "TEMPO", "duracao_min": 70, "descricao": "x" * 300}],
            desc_max=50,
        )
        assert "x" * 50 in linhas[0]
        assert "x" * 51 not in linhas[0]
