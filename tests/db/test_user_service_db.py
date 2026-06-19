"""Testes da camada de dados de usuários (user_service) com Mongo fake."""
import pytest

from app.services import user_service


def _dados_basicos(**over):
    d = {
        "login": "Gean",
        "senha": "senha123",
        "nome": "Gean Bedin",
        "telefone": "+5554991450676",
        "perfil": {"idade": 30, "peso_kg": 80, "altura_cm": 180, "fc_max": 190},
        "preferencias": {"objetivo": "performance_mtb", "dias_treino": [0, 2, 4]},
    }
    d.update(over)
    return d


class TestCriarUsuario:
    async def test_cria_e_normaliza_login(self, fake_db):
        u = await user_service.criar_usuario(_dados_basicos())
        assert u["login"] == "gean"  # lowercase
        assert "senha_hash" not in u  # nunca devolve o hash
        assert u["telefone_verificado"] is False

    async def test_deriva_zonas_de_fc_max(self, fake_db):
        u = await user_service.criar_usuario(_dados_basicos())
        assert u["zonas"]["fc_max"] == 190
        assert len(u["zonas"]["zonas"]) == 5

    async def test_horarios_default_aplicados(self, fake_db):
        u = await user_service.criar_usuario(_dados_basicos())
        assert "cafe" in u["horarios"]
        assert "jantar" in u["horarios"]

    async def test_login_duplicado_lanca(self, fake_db):
        await user_service.criar_usuario(_dados_basicos())
        with pytest.raises(ValueError):
            await user_service.criar_usuario(_dados_basicos(telefone="+5554000000000"))

    async def test_senha_e_hasheada(self, fake_db):
        await user_service.criar_usuario(_dados_basicos())
        doc = await user_service.get_por_login("gean")
        assert doc["senha_hash"] != "senha123"
        assert user_service.verificar_senha("senha123", doc["senha_hash"])


class TestBuscas:
    async def test_get_por_id(self, fake_db):
        u = await user_service.criar_usuario(_dados_basicos())
        achado = await user_service.get_por_id(u["_id"])
        assert achado["login"] == "gean"
        assert "senha_hash" not in achado

    async def test_get_por_id_invalido_retorna_none(self, fake_db):
        assert await user_service.get_por_id("nao-existe") is None

    async def test_get_por_login_case_insensitive(self, fake_db):
        await user_service.criar_usuario(_dados_basicos())
        assert (await user_service.get_por_login("GEAN")) is not None

    async def test_get_por_telefone(self, fake_db):
        await user_service.criar_usuario(_dados_basicos())
        u = await user_service.get_por_telefone("+5554991450676")
        assert u["login"] == "gean"


class TestAtualizar:
    async def test_atualiza_campos(self, fake_db):
        u = await user_service.criar_usuario(_dados_basicos())
        await user_service.atualizar_usuario(u["_id"], {"telefone_verificado": True})
        achado = await user_service.get_por_id(u["_id"])
        assert achado["telefone_verificado"] is True

    async def test_atualiza_campo_aninhado(self, fake_db):
        u = await user_service.criar_usuario(_dados_basicos())
        await user_service.atualizar_usuario(u["_id"], {"features.chat": False})
        achado = await user_service.get_por_id(u["_id"])
        assert achado["features"]["chat"] is False


class TestTelefoneNotificavel:
    async def test_none_se_telefone_nao_verificado(self, fake_db):
        u = await user_service.criar_usuario(_dados_basicos())
        # recém-criado: telefone_verificado False
        assert await user_service.telefone_notificavel(u["_id"]) is None

    async def test_none_se_whatsapp_inativo(self, fake_db):
        u = await user_service.criar_usuario(_dados_basicos())
        await user_service.atualizar_usuario(u["_id"], {"telefone_verificado": True})
        # whatsapp.ativo ainda False → não notifica
        assert await user_service.telefone_notificavel(u["_id"]) is None

    async def test_devolve_telefone_quando_verificado_e_ativo(self, fake_db):
        u = await user_service.criar_usuario(_dados_basicos())
        await user_service.atualizar_usuario(
            u["_id"], {"telefone_verificado": True, "whatsapp.ativo": True})
        tel = await user_service.telefone_notificavel(u["_id"])
        assert tel == "+5554991450676"

    async def test_none_para_usuario_inexistente(self, fake_db):
        assert await user_service.telefone_notificavel("000000000000000000000000") is None


class TestListar:
    async def test_lista_sem_senha(self, fake_db):
        await user_service.criar_usuario(_dados_basicos())
        await user_service.criar_usuario(_dados_basicos(login="outro", telefone="+5554111111111"))
        todos = await user_service.listar_usuarios()
        assert len(todos) == 2
        assert all("senha_hash" not in u for u in todos)
