"""Reavaliação de treino quando a FC não é confiável (sem cinta / cinta sem bateria).

Pedido do atleta: "ignora a FC de ontem, a cinta estava sem bateria" — a nota e
a análise têm que ser refeitas sem FC, e o TSS não pode continuar saindo de um
hrTSS calculado sobre um dado que não existiu.

Cobre as três portas de entrada: chat (ferramenta), preferência de perfil e a
propagação para o sync do Garmin.
"""
import pytest
from bson import ObjectId

import app.services.ai_service as ai
import app.services.avaliacao_service as aval
import app.services.chat_service as chat
from app.services.garmin_service import _metricas_extra

SEG = "2026-06-22"  # segunda
TER = "2026-06-23"
UID = "6a2ec0cf1a2b3c4d5e6f7a01"  # ObjectId válido: o perfil vive em db.users


@pytest.fixture
def _ia_fake(monkeypatch):
    """Captura o `ignorar_fc` recebido e devolve uma análise determinística."""
    chamadas = []

    async def _fake(planejado, resultado, user_id=None, fit_path=None, ignorar_fc=None):
        chamadas.append({"ignorar_fc": ignorar_fc, "resultado": resultado})
        return {"nota": 8.5, "resumo": "ok", "pontos_fortes": [], "pontos_fracos": []}

    monkeypatch.setattr(ai, "analisar_atividade_pos_treino", _fake)
    return chamadas


async def _seed(fake_db, resultado=None, tipo="TIROS"):
    await fake_db.semanas.insert_one({
        "semana_inicio": SEG, "user_id": UID, "objetivo": "",
        "treinos": [{
            "data": TER, "tipo": tipo, "duracao_min": 60,
            "descricao": "6x3min forte",
            "resultado": resultado if resultado is not None else {
                "duracao_min": 58, "distancia_km": 30, "avg_hr": 118, "max_hr": 131,
                "tss_obtido": 40,
                "analise_ia": {"nota": 4.0, "resumo": "faltou intensidade",
                               "pontos_fortes": [], "pontos_fracos": ["FC não subiu"]},
            },
        }],
    })


class TestFlags:
    async def test_marcacao_no_treino_ignora_fc(self, fake_db):
        assert await aval.deve_ignorar_fc(UID, {"fc_invalida": True}) is True

    async def test_sem_marcacao_e_sem_preferencia_usa_fc(self, fake_db):
        assert await aval.deve_ignorar_fc(UID, {"avg_hr": 150}) is False

    async def test_preferencia_sem_cinta_vale_para_todo_treino(self, fake_db):
        await fake_db.users.insert_one(
            {"_id": ObjectId(UID), "nome": "Atleta", "preferencias": {"sem_cinta_fc": True}})
        assert await aval.deve_ignorar_fc(UID, {"avg_hr": 150}) is True

    async def test_definir_uso_cinta_grava_preferencia(self, fake_db):
        await fake_db.users.insert_one({"_id": ObjectId(UID), "nome": "Atleta"})
        assert await aval.definir_uso_cinta(UID, usa_cinta=False) is True
        u = await fake_db.users.find_one({"_id": ObjectId(UID)})
        assert u["preferencias"]["sem_cinta_fc"] is True
        await aval.definir_uso_cinta(UID, usa_cinta=True)
        u = await fake_db.users.find_one({"_id": ObjectId(UID)})
        assert u["preferencias"]["sem_cinta_fc"] is False


class TestReavaliar:
    async def test_marca_treino_e_salva_nova_analise(self, fake_db, _ia_fake):
        await _seed(fake_db)
        r = await aval.reavaliar_treino(UID, TER, True, "cinta sem bateria")

        assert r["fc_invalida"] is True
        assert r["nota"] == 8.5
        assert _ia_fake[0]["ignorar_fc"] is True

        doc = await fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": UID})
        res = doc["treinos"][0]["resultado"]
        assert res["fc_invalida"] is True
        assert res["fc_invalida_motivo"] == "cinta sem bateria"
        assert res["analise_ia"]["nota"] == 8.5
        # A FC medida continua salva — só deixa de contar na avaliação.
        assert res["avg_hr"] == 118

    async def test_tss_por_fc_e_descartado(self, fake_db, _ia_fake):
        await _seed(fake_db)
        r = await aval.reavaliar_treino(UID, TER, True)
        # Sem potência, não sobra TSS confiável: melhor ausente que errado.
        assert r["tss_obtido"] is None
        doc = await fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": UID})
        assert "tss_obtido" not in doc["treinos"][0]["resultado"]

    async def test_desmarcar_volta_a_considerar_fc(self, fake_db, _ia_fake):
        await _seed(fake_db, resultado={
            "duracao_min": 58, "avg_hr": 118, "max_hr": 131,
            "fc_invalida": True, "fc_invalida_motivo": "cinta sem bateria",
        })
        r = await aval.reavaliar_treino(UID, TER, False)
        assert r["fc_invalida"] is False
        assert _ia_fake[0]["ignorar_fc"] is False
        res = (await fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": UID}))["treinos"][0]["resultado"]
        assert "fc_invalida" not in res
        assert "fc_invalida_motivo" not in res

    async def test_sem_resultado_da_erro_claro(self, fake_db, _ia_fake):
        await _seed(fake_db, resultado={})
        with pytest.raises(ValueError, match="resultado"):
            await aval.reavaliar_treino(UID, TER, True)

    async def test_data_sem_treino_da_erro(self, fake_db, _ia_fake):
        await _seed(fake_db)
        with pytest.raises(ValueError):
            await aval.reavaliar_treino(UID, "2026-06-25", True)

    async def test_nao_toca_no_treino_de_outro_usuario(self, fake_db, _ia_fake):
        await _seed(fake_db)
        with pytest.raises(ValueError):
            await aval.reavaliar_treino("6a2ec0cf1a2b3c4d5e6f7a02", TER, True)
        res = (await fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": UID}))["treinos"][0]["resultado"]
        assert "fc_invalida" not in res


class TestFerramentaChat:
    async def test_chat_reavalia_ignorando_fc(self, fake_db, _ia_fake):
        await _seed(fake_db)
        saida = await chat._executar_ferramenta(
            UID, "reavaliar_treino",
            {"data": TER, "ignorar_fc": True, "motivo": "cinta sem bateria"},
        )
        assert "8.5" in saida
        assert "sem considerar a FC" in saida
        res = (await fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": UID}))["treinos"][0]["resultado"]
        assert res["fc_invalida"] is True

    async def test_ignorar_fc_e_o_padrao_da_ferramenta(self, fake_db, _ia_fake):
        await _seed(fake_db)
        await chat._executar_ferramenta(UID, "reavaliar_treino", {"data": TER})
        assert _ia_fake[0]["ignorar_fc"] is True

    async def test_erro_vira_mensagem_e_nao_excecao(self, fake_db, _ia_fake):
        await _seed(fake_db)
        saida = await chat._executar_ferramenta(
            UID, "reavaliar_treino", {"data": "2026-06-25"})
        assert saida.startswith("Erro")

    async def test_configurar_cinta_reavalia_recentes(self, fake_db, _ia_fake, monkeypatch):
        from datetime import date
        import app.utils as utils
        monkeypatch.setattr(utils, "hoje_local", lambda: date(2026, 6, 24))
        await fake_db.users.insert_one({"_id": ObjectId(UID), "nome": "Atleta"})
        await _seed(fake_db)

        saida = await chat._executar_ferramenta(
            UID, "configurar_cinta_fc",
            {"usa_cinta": False, "reavaliar_ultimos_dias": 14},
        )
        assert "NÃO usa cinta" in saida
        u = await fake_db.users.find_one({"_id": ObjectId(UID)})
        assert u["preferencias"]["sem_cinta_fc"] is True
        res = (await fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": UID}))["treinos"][0]["resultado"]
        assert res["fc_invalida"] is True
        assert res["analise_ia"]["nota"] == 8.5

    async def test_ferramentas_expostas_ao_modelo(self):
        nomes = {t["name"] for t in chat._TOOLS}
        assert {"reavaliar_treino", "configurar_cinta_fc"} <= nomes
        # O bloco cacheável precisa terminar na última ferramenta da lista.
        assert "cache_control" in chat._TOOLS[-1]
        assert sum("cache_control" in t for t in chat._TOOLS) == 1


class TestMetricasTSS:
    def test_hrtss_descartado_sem_fc_confiavel(self):
        planejado = {"tipo": "TIROS", "duracao_min": 60}
        resultado = {"duracao_min": 60, "avg_hr": 120}
        com_fc = _metricas_extra(planejado, resultado, limiar=170)
        sem_fc = _metricas_extra(planejado, resultado, limiar=170, ignorar_fc=True)
        assert com_fc["tss_obtido"] > 0
        assert "tss_obtido" not in sem_fc
        # O TSS esperado (do planejado) não depende de FC e continua lá.
        assert sem_fc["tss_esperado"] == com_fc["tss_esperado"]

    def test_ptss_sobrevive_sem_fc(self):
        planejado = {"tipo": "TIROS", "duracao_min": 60}
        resultado = {"duracao_min": 60, "avg_hr": 120, "norm_power": 220}
        sem_fc = _metricas_extra(planejado, resultado, limiar=170, ftp=250, ignorar_fc=True)
        assert sem_fc["tss_obtido"] > 0


class TestAnaliseSemFC:
    def test_fallback_nao_cobra_intensidade_sem_fc(self):
        planejado = {"tipo": "TIROS", "duracao_min": 60}
        resultado = {"duracao_min": 60, "avg_hr": 118, "max_hr": 131}

        com_fc = ai._fallback_pos_treino(planejado, resultado)
        sem_fc = ai._fallback_pos_treino(planejado, resultado, ignorar_fc=True)

        assert any("intensidade" in p for p in com_fc["pontos_fracos"])
        assert not any("intensidade" in p for p in sem_fc["pontos_fracos"])
        assert "FC" not in sem_fc["resumo"] or "sem os dados de FC" in sem_fc["resumo"]
        assert sem_fc["nota"] > com_fc["nota"]

    async def test_prompt_omite_fc_e_instrui_a_nao_penalizar(self, fake_db, monkeypatch):
        capturado = {}

        class _Resp:
            content = [type("B", (), {"text": '{"nota": 7, "resumo": "r", '
                                              '"pontos_fortes": [], "pontos_fracos": []}'})()]

        async def _create(**kwargs):
            capturado["prompt"] = kwargs["messages"][0]["content"]
            return _Resp()

        monkeypatch.setattr(ai._client.messages, "create", _create)

        await ai.analisar_atividade_pos_treino(
            {"tipo": "TIROS", "duracao_min": 60},
            {"duracao_min": 60, "avg_hr": 118, "max_hr": 131,
             "fc_invalida": True, "fc_invalida_motivo": "cinta sem bateria"},
            UID,
        )
        p = capturado["prompt"]
        assert "118" not in p and "131" not in p       # a FC ruim não vai ao modelo
        assert "cinta sem bateria" in p                # mas o motivo, sim
        assert "NÃO penalize a nota pela ausência de FC" in p
