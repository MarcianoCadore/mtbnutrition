"""Card "Alvo dos treinos no Garmin" — rota própria, separada do FTP.

O alvo (FC, watts ou os dois) morava dentro do card de FTP e ia junto no mesmo
POST. Isso confundia duas decisões diferentes: o FTP é um número medido, o alvo é
como o atleta quer treinar — e quem só usa FC não tem FTP nenhum para salvar.
Agora cada um tem seu card e sua rota.
"""
from bson import ObjectId


class TestRotaAlvo:
    def _seed_user(self, fake_db, uid, run):
        """Insere o doc do usuário para que atualizar_usuario encontre o registro."""
        run(fake_db.users.insert_one({"_id": ObjectId(uid)}))

    def test_salva_e_devolve_o_alvo(self, auth_client, fake_db, run):
        client, uid = auth_client
        self._seed_user(fake_db, uid, run)
        r = client.post("/workout/zonas/alvo", json={"modo": "ambos"})
        assert r.status_code == 200
        assert r.json()["potencia_modo"] == "ambos"

    def test_alvo_invalido_cai_no_padrao(self, auth_client, fake_db, run):
        client, uid = auth_client
        self._seed_user(fake_db, uid, run)
        r = client.post("/workout/zonas/alvo", json={"modo": "sei-la"})
        assert r.status_code == 200
        assert r.json()["potencia_modo"] == "indoor"

    def test_salvar_alvo_nao_exige_ftp(self, auth_client, fake_db, run):
        """Quem escolhe FC em todos os treinos nunca vai preencher um FTP."""
        client, uid = auth_client
        self._seed_user(fake_db, uid, run)
        r = client.post("/workout/zonas/alvo", json={"modo": "nunca"})
        assert r.status_code == 200
        assert client.get("/workout/zonas/dados").json()["potencia"] is None

    def test_dados_expoem_o_alvo_mesmo_sem_ftp(self, auth_client, fake_db, run):
        """Sem isso o select do portal mostraria a primeira opção como se fosse a
        escolha salva, e o próximo Salvar trocaria o alvo sem o atleta pedir."""
        client, uid = auth_client
        self._seed_user(fake_db, uid, run)
        client.post("/workout/zonas/alvo", json={"modo": "sempre"})

        d = client.get("/workout/zonas/dados").json()
        assert d["potencia"] is None          # nenhum FTP configurado
        assert d["potencia_modo"] == "sempre"

    def test_salvar_ftp_nao_reescreve_o_alvo(self, auth_client, fake_db, run):
        """Regressão do card unificado: salvar o FTP mandava o modo junto e
        derrubava a escolha do atleta."""
        client, uid = auth_client
        self._seed_user(fake_db, uid, run)
        client.post("/workout/zonas/alvo", json={"modo": "ambos"})

        client.post("/workout/zonas/ftp", json={"ftp": 300})

        d = client.get("/workout/zonas/dados").json()
        assert d["potencia_modo"] == "ambos"
        assert d["potencia"]["ftp"] == 300
