"""Limpeza dos cabeçalhos "TIPO — DATA" (nome do workout do app) na descrição.

Bug do round-trip de sync: ao enviar pro Garmin o app usa o nome "TIPO — DATA";
ao puxar de volta esse nome era prefixado na descrição e acumulava a cada
envia→puxa. Quando o foco do dia mudava (VO2MAX → RECUPERACAO), sobravam vários
cabeçalhos divergindo do tipo real. A limpeza tira só essas linhas de cabeçalho.
"""
from app.services.plano_semana_service import limpar_titulo_descricao as L


class TestLimparTitulo:
    def test_caso_reportado_recuperacao_com_vo2max(self):
        # Dado real: dia virou Recuperação mas a descrição carregava a prescrição
        # antiga de VO2max, com dois cabeçalhos acumulados no topo.
        s = (
            "RECUPERACAO — 2026-07-14\n"
            "VO2MAX — 2026-07-14\n"
            "15 min aquecimento progressivo: 8 min Z1, 5 min Z2, 2 min Z3. "
            "Sessão principal: 5×4 min Z5 | alvo >318W, cadência 90-100 rpm.\n\n"
            "🎯 Alvo — Outdoor (FC): Zona 1 107-141 · Zona 5 177-192 bpm"
        )
        out = L(s)
        assert "RECUPERACAO — 2026-07-14" not in out
        assert "VO2MAX — 2026-07-14" not in out
        # corpo e legenda intactos (o corpo continua sendo do foco antigo — isso é
        # correção de dado, não de cabeçalho; aqui garantimos que não some conteúdo)
        assert "15 min aquecimento" in out
        assert "🎯 Alvo — Outdoor (FC): Zona 1 107-141" in out

    def test_um_cabecalho_no_topo(self):
        assert L("VO2MAX — 2026-07-14\n4x4 min Z5 com 4 min recuperação Z2.") == \
            "4x4 min Z5 com 4 min recuperação Z2."

    def test_tipo_com_espaco(self):
        # "Z2_LONGO".replace("_", " ") = "Z2 LONGO"; "TESTE FTP" idem.
        assert L("Z2 LONGO — 2026-01-05\nBase aeróbica Z2.") == "Base aeróbica Z2."
        assert L("TESTE FTP — 2026-01-05\nTeste de 20 min.") == "Teste de 20 min."

    def test_legenda_de_alvos_preservada(self):
        # A legenda "🎯 Alvo — Outdoor…" também tem travessão, mas começa com emoji
        # e não é uma data ISO no fim → NÃO pode ser removida.
        s = "🎯 Alvo — Outdoor (FC): Zona 2 142-149 bpm"
        assert L(s) == s

    def test_travessao_no_corpo_nao_e_removido(self):
        # Linha de prescrição com travessão mas sem o formato "TIPO — DATA".
        s = "Recuperação de 4 min Z1-Z2 entre cada bloco — desça completamente."
        assert L(s) == s

    def test_data_sem_cabecalho_de_tipo_intacta(self):
        # Uma data solta numa frase não é cabeçalho.
        s = "Treino planejado para 2026-07-14 na parte da manhã."
        assert L(s) == s

    def test_idempotente(self):
        s = "VO2MAX — 2026-07-14\nVO2MAX — 2026-07-14\n4x4 min Z5."
        assert L(L(s)) == L(s) == "4x4 min Z5."

    def test_none_e_vazio(self):
        assert L(None) is None
        assert L("") == ""

    def test_so_cabecalho_vira_vazio(self):
        assert L("RECUPERACAO — 2026-07-14") == ""
