"""A página de perfil tem três formulários (perfil, academia, nutrição) e todos
postam em POST /workout/perfil, cada um mandando só o seu bloco.

Gravar todos os campos sempre fazia "Salvar perfil" apagar a configuração de
academia inteira e as metas de nutrição — o que não vinha no form virava
False/{}/None. Cada bloco só é gravado quando foi realmente enviado.
"""
import pytest
from bson import ObjectId

BASE = {"idade": "42", "peso_kg": "78", "altura_cm": "178",
        "sexo": "M", "objetivo": "performance_mtb"}


@pytest.fixture
def user_com_academia(auth_client, fake_db, run):
    client, uid = auth_client
    run(fake_db.users.insert_one({
        "_id": ObjectId(uid), "login": "atleta", "nome": "Atleta",
        "academia": {"treina": True, "frequencia_semanal": 2,
                     "disponibilidade": {"1": "manha"}, "nivel": "intermediario"},
        "nutricao": {"basal_metabolico": 1800, "meta_calorica_diaria": 2600},
    }))
    return client, uid


class TestBlocosIndependentes:
    def test_salvar_perfil_nao_apaga_academia(self, user_com_academia, fake_db, run):
        client, uid = user_com_academia

        r = client.post("/workout/perfil", data=BASE)
        assert r.status_code == 200

        u = run(fake_db.users.find_one({"_id": ObjectId(uid)}))
        assert u["academia"]["treina"] is True
        assert u["academia"]["nivel"] == "intermediario"
        assert u["academia"]["frequencia_semanal"] == 2
        assert u["academia"]["disponibilidade"] == {"1": "manha"}

    def test_salvar_perfil_nao_apaga_nutricao(self, user_com_academia, fake_db, run):
        client, uid = user_com_academia

        client.post("/workout/perfil", data=BASE)

        u = run(fake_db.users.find_one({"_id": ObjectId(uid)}))
        assert u["nutricao"]["basal_metabolico"] == 1800
        assert u["nutricao"]["meta_calorica_diaria"] == 2600

    def test_salvar_academia_nao_apaga_nutricao(self, user_com_academia, fake_db, run):
        client, uid = user_com_academia

        client.post("/workout/perfil", data={
            **BASE, "treina_academia": "1", "academia_freq": "1",
            "academia_nivel": "avancado",
        })

        u = run(fake_db.users.find_one({"_id": ObjectId(uid)}))
        assert u["nutricao"]["basal_metabolico"] == 1800
        assert u["academia"]["nivel"] == "avancado"
        assert u["academia"]["frequencia_semanal"] == 1

    def test_salvar_nutricao_nao_apaga_academia(self, user_com_academia, fake_db, run):
        client, uid = user_com_academia

        client.post("/workout/perfil", data={
            **BASE, "basal_metabolico": "1900", "meta_calorica_diaria": "2700",
        })

        u = run(fake_db.users.find_one({"_id": ObjectId(uid)}))
        assert u["academia"]["nivel"] == "intermediario"
        assert u["academia"]["treina"] is True
        assert u["nutricao"]["basal_metabolico"] == 1900


class TestNivel:
    def test_nivel_invalido_vira_vazio(self, user_com_academia, fake_db, run):
        client, uid = user_com_academia

        client.post("/workout/perfil", data={
            **BASE, "treina_academia": "1", "academia_freq": "0",
            "academia_nivel": "monstro",
        })

        u = run(fake_db.users.find_one({"_id": ObjectId(uid)}))
        assert u["academia"]["nivel"] == ""

    @pytest.mark.parametrize("nivel", ["nunca", "iniciante", "intermediario", "avancado"])
    def test_niveis_validos(self, user_com_academia, fake_db, run, nivel):
        client, uid = user_com_academia

        client.post("/workout/perfil", data={
            **BASE, "treina_academia": "1", "academia_freq": "0",
            "academia_nivel": nivel,
        })

        u = run(fake_db.users.find_one({"_id": ObjectId(uid)}))
        assert u["academia"]["nivel"] == nivel
