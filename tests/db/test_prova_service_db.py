"""Testes da camada de dados de provas (prova_service) com Mongo fake."""
import pytest

from app.services import prova_service

UID = "user-abc"


class TestCriarProva:
    async def test_cria_com_campos_minimos(self, fake_db):
        p = await prova_service.criar_prova(UID, {"nome": "XCO Serra", "data": "2026-08-01"})
        assert p["nome"] == "XCO Serra"
        assert p["user_id"] == UID
        assert p["focos"] is None
        assert "_id" in p

    async def test_exige_nome_e_data(self, fake_db):
        with pytest.raises(ValueError):
            await prova_service.criar_prova(UID, {"nome": "Sem data"})
        with pytest.raises(ValueError):
            await prova_service.criar_prova(UID, {"data": "2026-08-01"})


class TestListarEProxima:
    async def test_lista_ordenada_por_data(self, fake_db):
        await prova_service.criar_prova(UID, {"nome": "B", "data": "2026-09-01"})
        await prova_service.criar_prova(UID, {"nome": "A", "data": "2026-07-01"})
        provas = await prova_service.listar_provas(UID)
        assert [p["nome"] for p in provas] == ["A", "B"]

    async def test_lista_isola_por_usuario(self, fake_db):
        await prova_service.criar_prova(UID, {"nome": "Minha", "data": "2026-07-01"})
        await prova_service.criar_prova("outro", {"nome": "Dele", "data": "2026-07-01"})
        provas = await prova_service.listar_provas(UID)
        assert len(provas) == 1
        assert provas[0]["nome"] == "Minha"

    async def test_proxima_prova_a_partir_de_ref(self, fake_db):
        await prova_service.criar_prova(UID, {"nome": "Passada", "data": "2026-01-01"})
        await prova_service.criar_prova(UID, {"nome": "Futura", "data": "2026-12-01"})
        prox = await prova_service.proxima_prova(UID, ref="2026-06-19")
        assert prox["nome"] == "Futura"

    async def test_proxima_prova_none_se_todas_passadas(self, fake_db):
        await prova_service.criar_prova(UID, {"nome": "Velha", "data": "2026-01-01"})
        assert await prova_service.proxima_prova(UID, ref="2026-06-19") is None


class TestAtualizarRemover:
    async def test_atualiza_campo(self, fake_db):
        p = await prova_service.criar_prova(UID, {"nome": "X", "data": "2026-08-01"})
        await prova_service.atualizar_prova(UID, p["_id"], {"local": "Gramado"})
        provas = await prova_service.listar_provas(UID)
        assert provas[0]["local"] == "Gramado"

    async def test_atualizar_id_invalido_lanca(self, fake_db):
        with pytest.raises(ValueError):
            await prova_service.atualizar_prova(UID, "id-bobo", {"local": "X"})

    async def test_remove(self, fake_db):
        p = await prova_service.criar_prova(UID, {"nome": "X", "data": "2026-08-01"})
        await prova_service.remover_prova(UID, p["_id"])
        assert await prova_service.listar_provas(UID) == []

    async def test_remove_respeita_usuario(self, fake_db):
        p = await prova_service.criar_prova(UID, {"nome": "X", "data": "2026-08-01"})
        # outro usuário não consegue remover
        await prova_service.remover_prova("intruso", p["_id"])
        assert len(await prova_service.listar_provas(UID)) == 1
