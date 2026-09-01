"""O que o parecer pós-treino recebe sobre POTÊNCIA.

Regressão do VO2máx de 31/08/2026, avaliado com nota 5.5 e "os intervalos podem
não ter sido executados na intensidade prescrita" — num treino com 12% do tempo
em Z5/Z6, que o mesmo parecer elogiava dois itens acima.

Duas causas, as duas neste arquivo:
- o app mandava a potência MÉDIA rotulada como "IF (NP/FTP)". Com 207 W e FTP
  300, a IA leu IF 0.69 e aplicou a régua de esforço contínuo ("IF < 0.75 =
  Z2/recuperação"). A NP real era 243 W, IF 0.81;
- a régua de IF do prompt não tinha exceção para treino intervalado, embora a
  régua equivalente de FC média já tivesse.
"""
import pytest

import app.services.ai_service as ai


class _Bloco:
    type = "text"
    text = '{"nota": 8, "resumo": "ok", "pontos_fortes": [], "pontos_fracos": []}'


class _Resp:
    content = [_Bloco()]


@pytest.fixture
def prompt(monkeypatch):
    """Captura o prompt enviado à IA e finge um FTP de 300 W para o atleta."""
    capturado = {}

    async def _create(**kwargs):
        capturado["texto"] = kwargs["messages"][0]["content"]
        return _Resp()

    async def _zonas_potencia(_user_id):
        return {"ftp": 300, "zonas": [
            {"zona": 1, "nome": "Recuperação", "min": 0, "max": 165},
            {"zona": 5, "nome": "VO2max", "min": 316, "max": 360},
        ]}

    import app.services.config_service as cfg
    monkeypatch.setattr(ai._client.messages, "create", _create)
    monkeypatch.setattr(cfg, "get_zonas_potencia", _zonas_potencia)
    return capturado


PLANEJADO = {"tipo": "VO2MAX", "duracao_min": 63,
             "descricao": "15 min aquecimento. 8x30s all-out. 5x2 min VO2max. "
                          "Volta à calma 3 min Z1."}


class TestIFNuncaSaiDaMedia:
    async def test_sem_np_nao_existe_if(self, prompt):
        """Potência média não é NP: sem NP o prompt não pode oferecer um IF."""
        await ai.analisar_atividade_pos_treino(
            PLANEJADO,
            {"duracao_min": 66, "avg_power": 207, "norm_power": None,
             "fc_invalida": True},
            user_id="u1", ignorar_fc=True,
        )
        p = prompt["texto"]
        assert "IF (NP/FTP)" not in p
        assert "0.69" not in p
        assert "não tem NP gravada" in p

    async def test_com_np_o_if_sai_da_np(self, prompt):
        """243 W / 300 W = 0.81, não os 0.69 da média."""
        await ai.analisar_atividade_pos_treino(
            PLANEJADO,
            {"duracao_min": 66, "avg_power": 207, "norm_power": 243,
             "fc_invalida": True},
            user_id="u1", ignorar_fc=True,
        )
        assert "IF (NP/FTP): 0.81" in prompt["texto"]


class TestDiretrizesDeIntervalado:
    async def test_regua_de_if_tem_excecao_para_intervalado(self, prompt):
        await ai.analisar_atividade_pos_treino(
            PLANEJADO, {"duracao_min": 66, "avg_power": 207, "norm_power": 243},
            user_id="u1", ignorar_fc=True,
        )
        p = prompt["texto"]
        assert "INTERVALADA" in p
        assert "TEMPO EM ZONAS ALTAS" in p

    async def test_cadencia_so_conta_contra_alvo_prescrito(self, prompt):
        """73 rpm de média num pedal de trilha é o tempo sem pedalar, não
        cadência baixa."""
        await ai.analisar_atividade_pos_treino(
            PLANEJADO,
            {"duracao_min": 66, "cadencia_media_rpm": 73, "cadencia_max_rpm": 120},
            user_id="u1", ignorar_fc=True,
        )
        p = prompt["texto"]
        assert "cadência-alvo" in p
        assert "SEM pedalar" in p

    async def test_academia_nao_recebe_diretriz_de_cadencia(self, prompt):
        """Na academia não há pedivela — a diretriz não tem o que fazer ali."""
        await ai.analisar_atividade_pos_treino(
            {"tipo": "ACADEMIA", "duracao_min": 45, "descricao": "Agachamento 4x8"},
            {"duracao_min": 45, "relato": "Fiz tudo"},
            user_id="u1",
        )
        assert "SEM pedalar" not in prompt["texto"]
