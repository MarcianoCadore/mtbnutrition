"""Indoor/outdoor é conceito de treino de bike.

O toggle "🚵 Outdoor (FC) / 🏠 Indoor (Watts)" aparecia no card de um dia de
academia, e o endpoint aceitava: gravava `indoor` no dia de musculação e ainda
tentava subir um workout de ciclismo para o Garmin (só não estragava porque
ACADEMIA não tem builder). O card agora esconde o toggle e a rota recusa.
"""
import pytest

SEG = "2026-06-22"  # segunda
QUA = "2026-06-24"  # quarta


class TestMarcarIndoor:
    def test_academia_recusada(self, auth_client, fake_db, run):
        client, uid = auth_client
        run(fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": uid, "objetivo": "",
            "treinos": [{"data": QUA, "tipo": "ACADEMIA", "duracao_min": 40,
                         "descricao": "Agachamento 4x8"}],
        }))

        r = client.post(f"/workout/treino/{SEG}/{QUA}/indoor", json={"indoor": True})

        assert r.status_code == 400
        assert "academia" in r.json()["detail"].lower()

        # E nada foi gravado no dia.
        doc = run(fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": uid}))
        assert doc["treinos"][0].get("indoor") is None

    def test_descanso_continua_404(self, auth_client, fake_db, run):
        client, uid = auth_client
        run(fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": uid, "objetivo": "",
            "treinos": [{"data": QUA, "tipo": "DESCANSO", "duracao_min": None}],
        }))

        r = client.post(f"/workout/treino/{SEG}/{QUA}/indoor", json={"indoor": True})
        assert r.status_code == 404

    def test_treino_de_bike_aceito(self, auth_client, fake_db, run):
        client, uid = auth_client
        run(fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": uid, "objetivo": "",
            "treinos": [{"data": QUA, "tipo": "TIROS", "duracao_min": 60}],
        }))

        r = client.post(f"/workout/treino/{SEG}/{QUA}/indoor", json={"indoor": True})

        assert r.status_code == 200
        doc = run(fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": uid}))
        assert doc["treinos"][0]["indoor"] is True
