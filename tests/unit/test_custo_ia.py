"""Cálculo e registro do custo de IA por assinante."""
import pytest

from app.services import custo_ia_service as custo


class _Usage:
    def __init__(self, entrada=0, saida=0, leitura=0, escrita=0):
        self.input_tokens = entrada
        self.output_tokens = saida
        self.cache_read_input_tokens = leitura
        self.cache_creation_input_tokens = escrita


class _RespAnthropic:
    def __init__(self, **kw):
        self.usage = _Usage(**kw)


class _MetaGemini:
    def __init__(self, entrada, saida):
        self.prompt_token_count = entrada
        self.candidates_token_count = saida
        self.cached_content_token_count = 0


class _RespGemini:
    def __init__(self, entrada, saida):
        self.usage_metadata = _MetaGemini(entrada, saida)


class TestPreco:
    def test_modelo_conhecido(self):
        assert custo.preco_do_modelo("claude-opus-4-8") == {"in": 5.00, "out": 25.00}

    def test_sufixo_de_data_casa_por_prefixo(self):
        assert custo.preco_do_modelo("claude-haiku-4-5-20251001")["in"] == 1.00

    def test_modelo_desconhecido_cai_no_padrao(self):
        assert custo.preco_do_modelo("modelo-que-nao-existe") == custo._PRECO_PADRAO


class TestCusto:
    def test_entrada_e_saida(self):
        # 1M entrada a $3 + 1M saída a $15 = $18
        assert custo.custo_usd("claude-sonnet-5",
                               {"entrada": 1_000_000, "saida": 1_000_000}) == pytest.approx(18.0)

    def test_cache_de_leitura_custa_um_decimo_da_entrada(self):
        """É o que faz o prompt caching valer a pena — se o cálculo cobrar
        preço cheio, o painel diz que cachear não adianta."""
        cheio = custo.custo_usd("claude-sonnet-5", {"entrada": 1_000_000})
        cache = custo.custo_usd("claude-sonnet-5", {"cache_leitura": 1_000_000})
        assert cache == pytest.approx(cheio * 0.10)

    def test_escrita_no_cache_custa_mais_que_entrada_normal(self):
        cheio = custo.custo_usd("claude-sonnet-5", {"entrada": 1_000_000})
        escrita = custo.custo_usd("claude-sonnet-5", {"cache_escrita": 1_000_000})
        assert escrita == pytest.approx(cheio * 1.25)

    def test_opus_custa_mais_que_sonnet(self):
        uso = {"entrada": 10_000, "saida": 2_000}
        assert custo.custo_usd("claude-opus-4-8", uso) > custo.custo_usd("claude-sonnet-5", uso)

    def test_uso_vazio_nao_custa(self):
        assert custo.custo_usd("claude-opus-4-8", {}) == 0.0


class TestExtrairUso:
    def test_resposta_anthropic(self):
        u = custo.extrair_uso(_RespAnthropic(entrada=100, saida=50, leitura=900, escrita=10))
        assert u == {"entrada": 100, "saida": 50, "cache_leitura": 900, "cache_escrita": 10}

    def test_resposta_gemini(self):
        u = custo.extrair_uso(_RespGemini(200, 80))
        assert u["entrada"] == 200 and u["saida"] == 80

    def test_objeto_sem_uso(self):
        assert custo.extrair_uso(object()) == {}


@pytest.mark.asyncio
class TestRegistro:
    async def test_grava_e_devolve_custo(self, fake_db):
        valor = await custo.registrar("u1", "chat", "claude-sonnet-5",
                                      _RespAnthropic(entrada=1000, saida=500))
        assert valor > 0
        doc = await fake_db.uso_ia.find_one({"user_id": "u1"})
        assert doc["feature"] == "chat"
        assert doc["modelo"] == "claude-sonnet-5"
        assert doc["entrada"] == 1000

    async def test_falha_de_telemetria_nao_derruba_a_chamada(self, fake_db, monkeypatch):
        """Registrar custo não pode impedir o atleta de receber o treino."""
        def _explode():
            raise RuntimeError("mongo fora do ar")
        monkeypatch.setattr(custo, "get_db", _explode)

        assert await custo.registrar("u1", "chat", "claude-sonnet-5",
                                     _RespAnthropic(entrada=10)) == 0.0

    async def test_resposta_sem_uso_nao_grava(self, fake_db):
        await custo.registrar("u1", "chat", "claude-sonnet-5", object())
        assert await fake_db.uso_ia.count_documents({}) == 0

    async def test_agrega_por_usuario_e_feature(self, fake_db):
        await custo.registrar("u1", "chat", "claude-sonnet-5", _RespAnthropic(entrada=1000))
        await custo.registrar("u1", "parecer_fisiologico", "claude-opus-4-8",
                              _RespAnthropic(entrada=5000, saida=2000))
        await custo.registrar("u2", "chat", "claude-sonnet-5", _RespAnthropic(entrada=500))

        por_usuario = await custo.custo_por_usuario()
        assert por_usuario["u1"]["chamadas"] == 2
        assert por_usuario["u1"]["custo_brl"] > por_usuario["u2"]["custo_brl"]

        features = {f["feature"]: f for f in await custo.custo_por_feature()}
        assert features["parecer_fisiologico"]["chamadas"] == 1

        total = await custo.total_do_mes()
        assert total["chamadas"] == 3
