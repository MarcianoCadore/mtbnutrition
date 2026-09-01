"""Ponte MyWhoosh → Garmin Connect.

O MyWhoosh não empurra para o Garmin (nativamente só para o Strava) e o caminho
do Strava chega sem .fit — sem potência, NP, zonas nem TSS. A ponte existe para
que o treino indoor caia no Garmin sozinho e o sync que já existe o avalie.

Nada aqui toca a rede: a API do MyWhoosh e o upload do Garmin são dublês.
"""
import httpx
import pytest
from bson import ObjectId

import app.services.mywhoosh_service as mw

UID = "6a2ec0cf1a2b3c4d5e6f7b02"
EMAIL = "atleta@exemplo.com"
SENHA = "senha-mywhoosh"

# .fit mínimo: o serviço só confere a assinatura ".FIT" nos bytes 8-11.
FIT = b"\x0e\x10\x00\x00\x00\x00\x00\x00.FIT\x00\x00rest-do-arquivo"

ATIVIDADE = {"id": "act-1", "activityFileId": "file-1", "name": "Ride"}


def _resposta(url, payload, status=200):
    # httpx exige o request na resposta para raise_for_status() funcionar.
    return httpx.Response(status, json=payload, request=httpx.Request("POST", url))


@pytest.fixture
def api(monkeypatch):
    """Dublê da API do MyWhoosh. `api["chamadas"]` guarda as URLs pedidas."""
    estado = {"chamadas": [], "atividades": [ATIVIDADE], "login_ok": True}

    async def _post(self, url, **kw):
        estado["chamadas"].append(url)
        if url == mw._LOGIN_URL:
            if not estado["login_ok"]:
                return _resposta(url, {"Success": False, "Message": "credenciais inválidas"})
            return _resposta(url, {"Success": True, "AccessToken": "tok",
                                   "RefreshToken": "rtok", "WhooshId": "wid"})
        if url == mw._ATIVIDADES_URL:
            return _resposta(url, {"data": {"results": estado["atividades"]}})
        if url == mw._DOWNLOAD_URL:
            return _resposta(url, {"data": "https://s3.exemplo.com/arquivo.fit"})
        raise AssertionError(f"URL inesperada: {url}")

    async def _get(self, url, **kw):
        estado["chamadas"].append(url)
        return httpx.Response(200, content=FIT, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", _post)
    monkeypatch.setattr(httpx.AsyncClient, "get", _get)
    return estado


@pytest.fixture
def garmin(monkeypatch):
    """Dublê do upload no Garmin. `garmin["subidas"]` guarda os arquivos."""
    estado = {"subidas": [], "erro": None}

    class _Api:
        def upload_activity(self, caminho):
            if estado["erro"]:
                raise estado["erro"]
            with open(caminho, "rb") as f:
                estado["subidas"].append(f.read())
            return {"ok": True}

    async def _cliente(_user_id):
        return _Api()

    import app.services.garmin_service as gs
    monkeypatch.setattr(gs, "get_garmin_client", _cliente)
    return estado


async def _conectado(fake_db):
    from app.services.crypto_service import cifrar
    await fake_db.users.insert_one({
        "_id": ObjectId(UID), "nome": "Atleta",
        "integracao": {"tipo": "garmin",
                       "mywhoosh": {"email": EMAIL, "senha_cifrada": cifrar(SENHA)}},
    })


class TestConectar:
    async def test_valida_antes_de_salvar(self, fake_db, api):
        await fake_db.users.insert_one({"_id": ObjectId(UID), "nome": "Atleta"})

        assert await mw.conectar(UID, EMAIL, SENHA) == {"ignoradas": 1}

        u = await fake_db.users.find_one({"_id": ObjectId(UID)})
        cfg = u["integracao"]["mywhoosh"]
        assert cfg["email"] == EMAIL
        assert cfg["senha_cifrada"] != SENHA, "a senha não pode ficar em claro"
        assert await mw.credenciais(UID) == (EMAIL, SENHA)

    async def test_credencial_ruim_nao_e_salva(self, fake_db, api):
        """Salvar uma senha que não funciona faria o job falhar de 10 em 10 min."""
        await fake_db.users.insert_one({"_id": ObjectId(UID), "nome": "Atleta"})
        api["login_ok"] = False

        with pytest.raises(mw.MyWhooshErro):
            await mw.conectar(UID, EMAIL, "errada")

        assert await mw.esta_conectado(UID) is False

    async def test_desconectar_apaga_a_credencial(self, fake_db, api):
        await _conectado(fake_db)
        await mw.desconectar(UID)
        assert await mw.esta_conectado(UID) is False


class TestPrimeiraConexao:
    """Conectar não é importar histórico.

    O pedido é "salvei o treino agora, sobe pro Garmin". Se conectar despejasse
    as últimas sessões, o Garmin ganharia de volta pedais que já estão lá — e
    alguns de meses atrás.
    """

    async def test_o_que_ja_existia_nao_sobe(self, fake_db, api, garmin):
        await fake_db.users.insert_one({"_id": ObjectId(UID), "nome": "Atleta"})

        r = await mw.conectar(UID, EMAIL, SENHA)

        assert r == {"ignoradas": 1}
        assert await mw.sync_para_garmin(UID) == 0
        assert garmin["subidas"] == [], "nada do histórico pode ir para o Garmin"

    async def test_treino_novo_depois_de_conectar_sobe(self, fake_db, api, garmin):
        await fake_db.users.insert_one({"_id": ObjectId(UID), "nome": "Atleta"})
        await mw.conectar(UID, EMAIL, SENHA)

        # O atleta pedala e salva: a sessão nova aparece no topo da lista.
        nova = {"id": "act-2", "activityFileId": "file-2", "name": "Ride de hoje"}
        api["atividades"] = [nova, ATIVIDADE]

        assert await mw.sync_para_garmin(UID) == 1
        assert garmin["subidas"] == [FIT]

    async def test_falha_ao_marcar_historico_nao_impede_conectar(self, fake_db, api, garmin,
                                                                monkeypatch):
        """Melhor conectar e arriscar um 409 do Garmin do que recusar a conexão."""
        await fake_db.users.insert_one({"_id": ObjectId(UID), "nome": "Atleta"})

        async def _explode(_sessao, _limite):
            raise mw.MyWhooshErro("API fora do ar")

        monkeypatch.setattr(mw, "_listar", _explode)

        assert await mw.conectar(UID, EMAIL, SENHA) == {"ignoradas": 0}
        assert await mw.esta_conectado(UID) is True


class TestSync:
    async def test_sobe_a_atividade_no_garmin(self, fake_db, api, garmin):
        await _conectado(fake_db)

        assert await mw.sync_para_garmin(UID) == 1
        assert garmin["subidas"] == [FIT]

    async def test_nao_sobe_a_mesma_atividade_duas_vezes(self, fake_db, api, garmin):
        """O job roda de 10 em 10 min e olha sempre as últimas atividades."""
        await _conectado(fake_db)

        assert await mw.sync_para_garmin(UID) == 1
        assert await mw.sync_para_garmin(UID) == 0
        assert len(garmin["subidas"]) == 1

    async def test_falha_no_upload_deixa_para_a_proxima_rodada(self, fake_db, api, garmin):
        """A reserva é devolvida: um erro de rede não pode perder o treino."""
        await _conectado(fake_db)
        garmin["erro"] = RuntimeError("500 do Garmin")

        assert await mw.sync_para_garmin(UID) == 0

        garmin["erro"] = None
        assert await mw.sync_para_garmin(UID) == 1

    async def test_duplicata_no_garmin_conta_como_sucesso(self, fake_db, api, garmin):
        """409 = o atleta já tinha subido na mão. Não é erro, e não repete."""
        await _conectado(fake_db)
        garmin["erro"] = RuntimeError("409 Conflict")

        assert await mw.sync_para_garmin(UID) == 1
        assert await mw.sync_para_garmin(UID) == 0

    async def test_sem_mywhoosh_conectado_nao_faz_nada(self, fake_db, api, garmin):
        """É o caso da maioria dos assinantes — e o job passa por todos."""
        await fake_db.users.insert_one({"_id": ObjectId(UID), "nome": "Atleta"})

        assert await mw.sync_para_garmin(UID) == 0
        assert api["chamadas"] == [], "nem login deve acontecer"

    async def test_atividade_sem_arquivo_e_pulada(self, fake_db, api, garmin):
        await _conectado(fake_db)
        api["atividades"] = [{"id": "act-2", "name": "Sessão sem fit"}]

        assert await mw.sync_para_garmin(UID) == 0
        assert garmin["subidas"] == []


class TestFormatoDaResposta:
    """A API do MyWhoosh já mudou de formato mais de uma vez."""

    @pytest.mark.parametrize("payload", [
        [ATIVIDADE],
        {"data": {"results": [ATIVIDADE]}},
        {"data": [ATIVIDADE]},
        {"activities": [ATIVIDADE]},
        {"results": [ATIVIDADE]},
    ])
    def test_extrai_a_lista(self, payload):
        assert mw._extrair_atividades(payload) == [ATIVIDADE]

    @pytest.mark.parametrize("payload", [{}, {"data": None}, None, "texto"])
    def test_formato_desconhecido_vira_lista_vazia(self, payload):
        assert mw._extrair_atividades(payload) == []

    @pytest.mark.parametrize("atividade,esperado", [
        ({"id": "a"}, "a"), ({"_id": "b"}, "b"), ({"activityId": 7}, "7"), ({}, None),
    ])
    def test_id_da_atividade(self, atividade, esperado):
        assert mw._id_da_atividade(atividade) == esperado


class TestArquivoInvalido:
    async def test_conteudo_que_nao_e_fit_e_recusado(self, fake_db, api, garmin, monkeypatch):
        """Uma página de erro do S3 não pode virar "treino" no Garmin."""
        await _conectado(fake_db)

        async def _get(self, url, **kw):
            return httpx.Response(200, content=b"<html>Access Denied</html>",
                                  request=httpx.Request("GET", url))

        monkeypatch.setattr(httpx.AsyncClient, "get", _get)

        assert await mw.sync_para_garmin(UID) == 0
        assert garmin["subidas"] == []
