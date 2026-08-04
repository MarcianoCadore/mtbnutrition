"""Academia nunca é julgada por frequência cardíaca.

Musculação não gera atividade para o Garmin sincronizar como o pedal gera: não
existe FC, potência, cadência nem TSS para a sessão. Julgar por FC seria julgar
por um dado que nunca foi medido — vale para QUALQUER origem do resultado, não
só para as sessões relatadas pelo atleta.
"""
import pytest

from app.services.plano_semana_service import (
    _resumo_treino, extrair_exercicios_academia,
)

DESCRICAO = """ACADEMIA — Força MTB (foco: pernas+core)

POR QUE HOJE: dia leve entre pedais.

EXERCÍCIOS:
1. Agachamento — 3x10
2. Abdutor — 3x12

OBSERVAÇÕES:
- Descanso 90s"""


class TestExtrairExercicios:
    def test_formato_da_casa(self):
        assert extrair_exercicios_academia(DESCRICAO) == [
            "1. Agachamento — 3x10", "2. Abdutor — 3x12",
        ]

    def test_texto_livre_nao_gera_lista(self):
        assert extrair_exercicios_academia("Musculação livre hoje") == []

    def test_vazio(self):
        assert extrair_exercicios_academia(None) == []
        assert extrair_exercicios_academia("") == []

    def test_observacoes_nao_viram_exercicio(self):
        itens = extrair_exercicios_academia(DESCRICAO)
        assert not any("Descanso" in i for i in itens)


class TestAnaliseForcaIgnorarFC:
    async def test_academia_ignora_fc_mesmo_com_dados(self, monkeypatch):
        """Mesmo que um resultado traga avg_hr, a academia é analisada sem FC."""
        import app.services.ai_service as ai
        capturado = {}

        class _Bloco:
            type = "text"
            text = '{"nota": 9, "resumo": "ok", "pontos_fortes": [], "pontos_fracos": []}'

        class _Resp:
            content = [_Bloco()]

        async def _create(**kwargs):
            capturado["prompt"] = kwargs["messages"][0]["content"]
            return _Resp()

        monkeypatch.setattr(ai._client.messages, "create", _create)

        await ai.analisar_atividade_pos_treino(
            {"tipo": "ACADEMIA", "duracao_min": 45, "descricao": DESCRICAO},
            {"duracao_min": 45, "avg_hr": 140, "max_hr": 165,
             "relato": "Fiz tudo, sensação 5/5"},
            user_id=None,
        )

        p = capturado["prompt"]
        # Nenhum valor de FC chega ao prompt: nem o da sessão, nem a FC máxima /
        # limiar do perfil (que são referências de bike). O único "bpm" que
        # sobra é a própria instrução de não citar FC.
        assert "140 bpm" not in p and "165 bpm" not in p
        assert "FC média" not in p and "FC máxima" not in p
        assert "Zonas de FC" not in p
        assert "MUSCULAÇÃO (ACADEMIA)" in p
        assert "PROGRESSÃO DE FORÇA" in p
        assert "Fiz tudo, sensação 5/5" in p            # o relato entrou

    async def test_treino_de_bike_continua_usando_fc(self, monkeypatch):
        import app.services.ai_service as ai
        capturado = {}

        class _Bloco:
            type = "text"
            text = '{"nota": 8, "resumo": "ok", "pontos_fortes": [], "pontos_fracos": []}'

        class _Resp:
            content = [_Bloco()]

        async def _create(**kwargs):
            capturado["prompt"] = kwargs["messages"][0]["content"]
            return _Resp()

        monkeypatch.setattr(ai._client.messages, "create", _create)

        await ai.analisar_atividade_pos_treino(
            {"tipo": "TIROS", "duracao_min": 60},
            {"duracao_min": 62, "avg_hr": 140, "max_hr": 178},
            user_id=None, ignorar_fc=False,
        )

        p = capturado["prompt"]
        assert "FC média: 140 bpm" in p
        assert "MUSCULAÇÃO (ACADEMIA)" not in p


class TestResumoParaOGerador:
    def test_execucao_vira_linha_de_progressao(self):
        txt = _resumo_treino({
            "data": "2026-06-24", "tipo": "ACADEMIA", "duracao_min": 45,
            "execucao": {"itens_feitos": [0, 1], "total_itens": 3, "sensacao": 4},
            "resultado": {"duracao_min": 45, "fc_invalida": True},
        })
        assert "Execução: 2/3 exercícios concluídos" in txt
        assert "sensação do atleta: 4/5" in txt
        assert "não use esses dados aqui" in txt
        # A linha genérica de FC não pode aparecer para academia.
        assert "sem dado confiável nesta sessão" not in txt

    def test_cargas_entram_casadas_pelo_nome(self):
        """É pelo nome que a carga de uma semana vira a prescrição da seguinte."""
        txt = _resumo_treino({
            "data": "2026-06-24", "tipo": "ACADEMIA", "duracao_min": 45,
            "descricao": """ACADEMIA — Força MTB (foco: pernas+core)

EXERCÍCIOS:
1. Agachamento — 3x10 — 20 kg (quadríceps)
2. Abdutor — 3x12 — 35 kg

OBSERVAÇÕES:
- Descanso 90s""",
            "execucao": {"itens_feitos": [0, 1], "total_itens": 2,
                         "cargas": {"0": 22.5, "1": 35.0}, "sensacao": 5},
        })
        assert "Cargas usadas: Agachamento 22.5kg; Abdutor 35.0kg" in txt

    def test_sem_carga_nao_gera_linha(self):
        txt = _resumo_treino({
            "data": "2026-06-24", "tipo": "ACADEMIA", "duracao_min": 45,
            "execucao": {"itens_feitos": [0], "total_itens": 2, "sensacao": 3},
        })
        assert "Cargas usadas" not in txt

    def test_academia_sem_registro(self):
        txt = _resumo_treino({"data": "2026-06-24", "tipo": "ACADEMIA", "duracao_min": 45})
        assert "sem registro do atleta" in txt

    def test_dia_duplo_nao_perde_a_academia(self):
        """Sem esta linha o dia duplo chegaria ao gerador como se só tivesse pedal."""
        txt = _resumo_treino({
            "data": "2026-06-24", "tipo": "RECUPERACAO", "duracao_min": 50,
            "descricao": "Pedal leve Z1", "periodo": "noite",
            "academia": {
                "duracao_min": 45, "periodo": "manha",
                "descricao": """ACADEMIA — Força MTB (foco: superior+core)

EXERCÍCIOS:
1. Remada — 3x10 — 30 kg
2. Prancha — 3x45s

OBSERVAÇÕES:
- Descanso 90s""",
                "execucao": {"itens_feitos": [0, 1], "total_itens": 2,
                             "cargas": {"0": 32.5}, "sensacao": 4},
            },
        })
        assert "+ ACADEMIA no mesmo dia (45 min, manha)" in txt
        assert "Execução: 2/2 exercícios concluídos" in txt
        assert "sensação do atleta: 4/5" in txt
        assert "Cargas usadas: Remada 32.5kg" in txt

    def test_dia_duplo_sem_registro(self):
        txt = _resumo_treino({
            "data": "2026-06-24", "tipo": "RECUPERACAO", "duracao_min": 50,
            "academia": {"duracao_min": 45, "descricao": "ACADEMIA — Força MTB"},
        })
        assert "+ ACADEMIA no mesmo dia" in txt
        assert "sem registro do atleta" in txt

    def test_bike_sem_academia_nao_ganha_linha(self):
        txt = _resumo_treino({
            "data": "2026-06-24", "tipo": "TIROS", "duracao_min": 60,
        })
        assert "ACADEMIA no mesmo dia" not in txt

    def test_bike_com_fc_invalida_mantem_a_linha_antiga(self):
        txt = _resumo_treino({
            "data": "2026-06-24", "tipo": "TIROS", "duracao_min": 60,
            "resultado": {"duracao_min": 62, "fc_invalida": True},
        })
        assert "sem dado confiável nesta sessão" in txt
