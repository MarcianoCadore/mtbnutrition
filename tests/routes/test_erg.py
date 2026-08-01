"""Endpoints de exportação ERG/XML (/workout/erg/...).

- /workout/erg/{tipo}                      → ERG por tipo (usado pelo gráfico do portal)
- /workout/erg/semana/{semana}/{data}      → ERG do treino agendado (nome/descrição reais)

Exigem FTP configurado (as potências saem em watts). Sem FTP → 400.
"""
import xml.etree.ElementTree as ET

from bson import ObjectId

SEG = "2026-06-22"  # segunda
QUA = "2026-06-24"  # quarta


def _seed_ftp(fake_db, run, uid, ftp=250):
    run(fake_db.users.insert_one({"_id": ObjectId(uid), "ftp": ftp}))


class TestErgPorTipo:
    def test_gera_xml_com_ftp(self, auth_client, fake_db, run):
        client, uid = auth_client
        _seed_ftp(fake_db, run, uid)

        r = client.get("/workout/erg/TIROS?duracao_min=62")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/xml")
        assert "attachment" in r.headers.get("content-disposition", "")
        root = ET.fromstring(r.text)          # bem-formado
        assert root.tag == "Workout"
        assert len(root.find("WorkoutSteps")) > 0
        assert len(root.find("Events")) > 0

    def test_sem_ftp_retorna_400(self, auth_client, fake_db, run):
        client, uid = auth_client  # sem seed de FTP
        r = client.get("/workout/erg/TIROS")
        assert r.status_code == 400
        assert "FTP" in r.json()["detail"]

    def test_tipo_desconhecido_404(self, auth_client, fake_db, run):
        client, uid = auth_client
        _seed_ftp(fake_db, run, uid)
        r = client.get("/workout/erg/NAO_EXISTE")
        assert r.status_code == 404


class TestErgTreinoAgendado:
    def test_usa_nome_do_treino_do_dia(self, auth_client, fake_db, run):
        client, uid = auth_client
        _seed_ftp(fake_db, run, uid)
        run(fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": uid, "objetivo": "",
            "treinos": [{"data": QUA, "tipo": "VO2MAX", "duracao_min": 62,
                         "nome": "VO2 da Quarta", "descricao": "Intervalos fortes"}],
        }))

        r = client.get(f"/workout/erg/semana/{SEG}/{QUA}")
        assert r.status_code == 200
        assert "vo2_da_quarta.xml" in r.headers.get("content-disposition", "")
        root = ET.fromstring(r.text)
        assert root.get("name") == "VO2 da Quarta"
        assert root.find("Metadata/Description").text == "Intervalos fortes"

    def test_data_sem_treino_404(self, auth_client, fake_db, run):
        client, uid = auth_client
        _seed_ftp(fake_db, run, uid)
        run(fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": uid, "objetivo": "", "treinos": [],
        }))
        r = client.get(f"/workout/erg/semana/{SEG}/{QUA}")
        assert r.status_code == 404

    def test_descanso_404(self, auth_client, fake_db, run):
        client, uid = auth_client
        _seed_ftp(fake_db, run, uid)
        run(fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": uid, "objetivo": "",
            "treinos": [{"data": QUA, "tipo": "DESCANSO"}],
        }))
        r = client.get(f"/workout/erg/semana/{SEG}/{QUA}")
        assert r.status_code == 404

    def test_ignora_treino_extra_e_usa_o_primario(self, auth_client, fake_db, run):
        client, uid = auth_client
        _seed_ftp(fake_db, run, uid)
        run(fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": uid, "objetivo": "",
            "treinos": [
                {"data": QUA, "tipo": "TEMPO", "duracao_min": 70, "nome": "Tempo primário"},
                {"data": QUA, "tipo": "ACADEMIA", "duracao_min": 60,
                 "origem": "extra", "id": "extra-1"},
            ],
        }))
        r = client.get(f"/workout/erg/semana/{SEG}/{QUA}")
        assert r.status_code == 200
        assert ET.fromstring(r.text).get("name") == "Tempo primário"
