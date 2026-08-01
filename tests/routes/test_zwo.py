"""Endpoints de exportação .zwo (/workout/zwo/...).

Diferença central para o ERG: o .zwo é RELATIVO ao FTP, então NÃO exige FTP
configurado — cada usuário autenticado baixa o seu próprio arquivo do dia.
"""
import xml.etree.ElementTree as ET

SEG = "2026-06-22"  # segunda
QUA = "2026-06-24"  # quarta


class TestZwoPorTipo:
    def test_gera_zwo_sem_ftp(self, auth_client, fake_db, run):
        client, uid = auth_client  # SEM seed de FTP — mesmo assim deve funcionar
        r = client.get("/workout/zwo/TIROS?duracao_min=62")
        assert r.status_code == 200
        assert "attachment" in r.headers.get("content-disposition", "")
        assert ".zwo" in r.headers.get("content-disposition", "")
        root = ET.fromstring(r.text)
        assert root.tag == "workout_file"
        assert len(root.find("workout")) > 0

    def test_tipo_desconhecido_404(self, auth_client, fake_db, run):
        client, uid = auth_client
        r = client.get("/workout/zwo/NAO_EXISTE")
        assert r.status_code == 404


class TestZwoTreinoAgendado:
    def test_cada_usuario_baixa_o_seu(self, auth_client, fake_db, run):
        client, uid = auth_client
        run(fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": uid, "objetivo": "",
            "treinos": [{"data": QUA, "tipo": "VO2MAX", "duracao_min": 62,
                         "nome": "Meu VO2", "descricao": "Forte"}],
        }))
        r = client.get(f"/workout/zwo/semana/{SEG}/{QUA}")
        assert r.status_code == 200
        assert "meu_vo2.zwo" in r.headers.get("content-disposition", "")
        assert ET.fromstring(r.text).find("name").text == "Meu VO2"

    def test_treino_de_outro_usuario_nao_vaza(self, auth_client, fake_db, run):
        client, uid = auth_client
        # Semana pertence a OUTRO usuário — o endpoint escopa por user_id → 404.
        run(fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": "outro-usuario", "objetivo": "",
            "treinos": [{"data": QUA, "tipo": "VO2MAX", "duracao_min": 62}],
        }))
        r = client.get(f"/workout/zwo/semana/{SEG}/{QUA}")
        assert r.status_code == 404

    def test_data_sem_treino_404(self, auth_client, fake_db, run):
        client, uid = auth_client
        run(fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": uid, "objetivo": "", "treinos": [],
        }))
        r = client.get(f"/workout/zwo/semana/{SEG}/{QUA}")
        assert r.status_code == 404

    def test_ignora_extra_e_usa_primario(self, auth_client, fake_db, run):
        client, uid = auth_client
        run(fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": uid, "objetivo": "",
            "treinos": [
                {"data": QUA, "tipo": "TEMPO", "duracao_min": 70, "nome": "Tempo primário"},
                {"data": QUA, "tipo": "ACADEMIA", "origem": "extra", "id": "x1"},
            ],
        }))
        r = client.get(f"/workout/zwo/semana/{SEG}/{QUA}")
        assert r.status_code == 200
        assert ET.fromstring(r.text).find("name").text == "Tempo primário"
