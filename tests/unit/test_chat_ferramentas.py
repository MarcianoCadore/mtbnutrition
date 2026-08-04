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
