"""A página de perfil tem quatro formulários (perfil, dias de treino, academia,
nutrição) e todos postam em POST /workout/perfil, cada um mandando só o seu bloco.

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


class TestDiasDeTreino:
    """Bloco 'Disponibilidade para treinar' — é o que manda no gerador."""

    def test_salva_dias_e_frequencia(self, user_com_academia, fake_db, run):
        client, uid = user_com_academia

        r = client.post("/workout/perfil", data={
            **BASE, "bike_freq": "3", "bike_dias": "1,3,5"})
        assert r.status_code == 200

        u = run(fake_db.users.find_one({"_id": ObjectId(uid)}))
        assert u["preferencias"]["dias_treino"] == [1, 3, 5]
        assert u["preferencias"]["frequencia_semanal"] == 3

    def test_salvar_perfil_nao_apaga_dias_de_treino(self, user_com_academia, fake_db, run):
        client, uid = user_com_academia
        client.post("/workout/perfil", data={
            **BASE, "bike_freq": "3", "bike_dias": "1,3,5"})

        client.post("/workout/perfil", data=BASE)

        u = run(fake_db.users.find_one({"_id": ObjectId(uid)}))
        assert u["preferencias"]["dias_treino"] == [1, 3, 5]

    def test_dias_vazios_nao_zeram_a_configuracao(self, user_com_academia, fake_db, run):
        client, uid = user_com_academia
        client.post("/workout/perfil", data={
            **BASE, "bike_freq": "3", "bike_dias": "1,3,5"})

        client.post("/workout/perfil", data={
            **BASE, "bike_freq": "0", "bike_dias": ""})

        u = run(fake_db.users.find_one({"_id": ObjectId(uid)}))
        assert u["preferencias"]["dias_treino"] == [1, 3, 5]

    def test_dias_invalidos_sao_descartados(self, user_com_academia, fake_db, run):
        client, uid = user_com_academia

        client.post("/workout/perfil", data={
            **BASE, "bike_freq": "9", "bike_dias": "0,9,x,,6,6"})

        u = run(fake_db.users.find_one({"_id": ObjectId(uid)}))
        assert u["preferencias"]["dias_treino"] == [0, 6]
        assert u["preferencias"]["frequencia_semanal"] == 2   # freq inválida → nº de dias


class TestMetaDeVolume:
    """Meta de horas por semana — opcional: em branco = a IA decide o volume."""

    def test_salva_a_meta_em_minutos(self, user_com_academia, fake_db, run):
        client, uid = user_com_academia

        r = client.post("/workout/perfil", data={
            **BASE, "bike_freq": "5", "bike_dias": "0,1,2,3,5",
            "volume_semanal_h": "10"})
        assert r.status_code == 200

        u = run(fake_db.users.find_one({"_id": ObjectId(uid)}))
        assert u["preferencias"]["volume_semanal_min"] == 600

    def test_aceita_meia_hora_com_virgula(self, user_com_academia, fake_db, run):
        client, uid = user_com_academia

        client.post("/workout/perfil", data={
            **BASE, "bike_dias": "0,2,4", "volume_semanal_h": "10,5"})

        u = run(fake_db.users.find_one({"_id": ObjectId(uid)}))
        assert u["preferencias"]["volume_semanal_min"] == 630

    @pytest.mark.parametrize("valor", ["", "0", "abc", "99", "0.5", "-3"])
    def test_vazio_ou_invalido_deixa_a_ia_decidir(self, user_com_academia, fake_db, run, valor):
        client, uid = user_com_academia

        client.post("/workout/perfil", data={
            **BASE, "bike_dias": "0,2,4", "volume_semanal_h": valor})

        u = run(fake_db.users.find_one({"_id": ObjectId(uid)}))
        assert u["preferencias"]["volume_semanal_min"] is None

    def test_meta_pode_ser_desligada_depois_de_ligada(self, user_com_academia, fake_db, run):
        client, uid = user_com_academia
        client.post("/workout/perfil", data={
            **BASE, "bike_dias": "0,2,4", "volume_semanal_h": "10"})

        client.post("/workout/perfil", data={
            **BASE, "bike_dias": "0,2,4", "volume_semanal_h": ""})

        u = run(fake_db.users.find_one({"_id": ObjectId(uid)}))
        assert u["preferencias"]["volume_semanal_min"] is None

    def test_salvar_outro_bloco_nao_apaga_a_meta(self, user_com_academia, fake_db, run):
        client, uid = user_com_academia
        client.post("/workout/perfil", data={
            **BASE, "bike_dias": "0,2,4", "volume_semanal_h": "10"})

        client.post("/workout/perfil", data=BASE)                      # bloco perfil
        client.post("/workout/perfil", data={**BASE, "treina_academia": "1"})

        u = run(fake_db.users.find_one({"_id": ObjectId(uid)}))
        assert u["preferencias"]["volume_semanal_min"] == 600

    def test_pagina_traz_a_meta_preenchida(self, user_com_academia, run, fake_db):
        client, uid = user_com_academia
        client.post("/workout/perfil", data={
            **BASE, "bike_dias": "0,2,4", "volume_semanal_h": "10"})

        html = client.get("/workout/perfil").text
        assert 'id="volume_semanal_h"' in html
        assert 'value="10"' in html

    def test_pagina_sem_meta_deixa_o_campo_vazio(self, user_com_academia):
        client, _ = user_com_academia
        html = client.get("/workout/perfil").text
        assert 'id="volume_semanal_h"' in html
        assert "{{VOLUME_SEMANAL_H}}" not in html


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
