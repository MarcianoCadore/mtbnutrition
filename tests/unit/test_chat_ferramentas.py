"""Ligação entre as ferramentas do chat e os serviços.

`_executar_ferramenta` engole exceções e devolve "Erro inesperado: ..." como se
fosse um resultado normal — um erro de fiação (nome de arg trocado, import
errado) passaria despercebido e o chat responderia como se tivesse funcionado.
Estes testes exercitam a fiação de verdade contra o banco fake.
"""
import pytest

import app.services.chat_service as chat

UID = "user-ferramentas"
SEG = "2026-06-22"  # segunda
QUA = "2026-06-24"  # quarta


@pytest.fixture(autouse=True)
def _sem_ia(monkeypatch):
    import app.services.ai_service as ai

    async def _fake(planejado, resultado, user_id=None, fit_path=None, ignorar_fc=None):
        return {"nota": 7.5, "resumo": "Volume cumprido.",
                "pontos_fortes": ["Executou tudo"], "pontos_fracos": []}

    monkeypatch.setattr(ai, "analisar_atividade_pos_treino", _fake)


class TestRegistrarTreinoRealizado:
    async def test_registra_e_preserva_o_plano(self, fake_db):
        await fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": UID, "objetivo": "",
            "treinos": [{"data": QUA, "tipo": "ACADEMIA", "duracao_min": 40,
                         "descricao": "Agachamento 4x8, supino 3x10"}],
        })

        saida = await chat._executar_ferramenta(UID, "registrar_treino_realizado", {
            "data": QUA, "relato": "Fiz todos os exercícios, me senti muito bem",
            "duracao_min": 40,
        })

        assert "Erro" not in saida
        assert "REALIZADO" in saida
        assert "Nota: 7.5" in saida

        doc = await fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": UID})
        t = doc["treinos"][0]
        assert t["descricao"] == "Agachamento 4x8, supino 3x10"  # plano intacto
        assert t["resultado"]["origem"] == "relato_atleta"

    async def test_erro_vira_mensagem_legivel(self, fake_db):
        """Sem semana no banco o chat precisa saber que NÃO registrou."""
        saida = await chat._executar_ferramenta(UID, "registrar_treino_realizado", {
            "data": QUA, "relato": "Fiz academia",
        })
        assert saida.startswith("Erro:")


class TestVerSemana:
    async def test_mostra_academia_e_extras(self, fake_db):
        await fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": UID, "objetivo": "",
            "treinos": [
                {"data": QUA, "tipo": "ACADEMIA", "duracao_min": 50, "origem": "extra"},
                {"data": QUA, "tipo": "Z2_LONGO", "duracao_min": 90, "descricao": "Base Z2",
                 "academia": {"duracao_min": 45, "descricao": "Core"}},
            ],
        })

        saida = await chat._executar_ferramenta(UID, "ver_semana", {"semana_inicio": SEG})

        linhas = saida.splitlines()
        assert "[Z2_LONGO] PLANEJADO 90min" in linhas[0]
        assert "+ ACADEMIA 45min no mesmo dia" in linhas[1]
        assert "EXTRA" in linhas[2]


class TestAjustarTreino:
    """Encurtar um treino não pode reescrever o dia.

    Regressão de 31/08/2026: "diminui o treino de hoje para 1h03" só tinha
    `adicionar_treino` como saída, e ele reescreve o dia inteiro. O modelo passou
    tipo=RECUPERACAO num VO2máx, a cadência-alvo foi a zero junto e a avaliação
    do treino saiu comparando um treino de tiros com uma prescrição de
    recuperação.
    """

    PLANO = {"data": QUA, "tipo": "VO2MAX", "duracao_min": 78, "cadencia_rpm": "90-100",
             "periodo": "tarde", "descricao": "15 min aquecimento. 5x2 min VO2max. "
                                              "Volta à calma 15 min Z1.",
             "garmin_workout_id": "999"}

    async def _semana(self, fake_db, **extra):
        await fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": UID, "objetivo": "",
            "treinos": [{**self.PLANO, **extra}],
        })

    async def _treino(self, fake_db):
        doc = await fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": UID})
        return doc["treinos"][0]

    async def test_muda_so_a_duracao(self, fake_db):
        await self._semana(fake_db)

        saida = await chat._executar_ferramenta(UID, "ajustar_treino",
                                                {"data": QUA, "duracao_min": 63})

        assert "Erro" not in saida
        t = await self._treino(fake_db)
        assert t["duracao_min"] == 63
        assert t["tipo"] == "VO2MAX", "o tipo do treino não muda ao encurtar"
        assert t["cadencia_rpm"] == "90-100"
        assert t["periodo"] == "tarde"
        assert t["descricao"] == self.PLANO["descricao"]

    async def test_descricao_nova_acompanha_o_tempo_novo(self, fake_db):
        await self._semana(fake_db)

        await chat._executar_ferramenta(UID, "ajustar_treino", {
            "data": QUA, "duracao_min": 63,
            "descricao": "15 min aquecimento. 5x2 min VO2max. Volta à calma 3 min Z1.",
        })

        t = await self._treino(fake_db)
        assert t["duracao_min"] == 63
        assert "3 min Z1" in t["descricao"]
        assert t["tipo"] == "VO2MAX"

    async def test_treino_ja_realizado_mantem_o_agendamento(self, fake_db):
        """Ajuste retroativo (o atleta contando o que fez) não mexe no relógio."""
        await self._semana(fake_db, resultado={"duracao_min": 66})

        saida = await chat._executar_ferramenta(UID, "ajustar_treino",
                                                {"data": QUA, "duracao_min": 63})

        t = await self._treino(fake_db)
        assert t["garmin_workout_id"] == "999"
        assert "Garmin" not in saida

    async def test_treino_futuro_solta_o_agendamento(self, fake_db):
        """Duração nova = workout desatualizado no relógio: some o vínculo para o
        atleta reenviar pelo botão."""
        await self._semana(fake_db)

        saida = await chat._executar_ferramenta(UID, "ajustar_treino",
                                                {"data": QUA, "duracao_min": 100})

        t = await self._treino(fake_db)
        assert t["garmin_workout_id"] is None
        assert "reenvie" in saida

    async def test_dia_sem_treino_vira_erro(self, fake_db):
        saida = await chat._executar_ferramenta(UID, "ajustar_treino",
                                                {"data": QUA, "duracao_min": 60})
        assert saida.startswith("Erro:")

    async def test_sem_nada_para_ajustar_vira_erro(self, fake_db):
        await self._semana(fake_db)
        saida = await chat._executar_ferramenta(UID, "ajustar_treino", {"data": QUA})
        assert saida.startswith("Erro:")
