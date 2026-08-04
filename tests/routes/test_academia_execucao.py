"""Checklist de academia: o atleta marca os exercícios conforme executa e fecha
a sessão dando uma nota de 1 a 5 para como se sentiu.

Musculação não gera atividade para o Garmin sincronizar, então esse checklist é
o único registro da sessão — e dar a nota de sensação É o registro, não existe
botão separado de "registrar treino".
"""
import pytest

SEG = "2026-06-22"  # segunda
QUA = "2026-06-24"  # quarta

DESCRICAO = """ACADEMIA — Força MTB (foco: pernas+core)

POR QUE HOJE: dia leve entre pedais.

EXERCÍCIOS:
1. Agachamento — 3x10
2. Abdutor — 3x12
3. Panturrilha — 4x15

OBSERVAÇÕES:
- Descanso 90s entre séries"""


@pytest.fixture(autouse=True)
def _sem_ia(monkeypatch):
    import app.services.ai_service as ai

    async def _fake(planejado, resultado, user_id=None, fit_path=None, ignorar_fc=None):
        return {"nota": 9.0, "resumo": "Tudo executado.",
                "pontos_fortes": [], "pontos_fracos": []}

    monkeypatch.setattr(ai, "analisar_atividade_pos_treino", _fake)


def _semana(uid, treino=None):
    return {
        "semana_inicio": SEG, "user_id": uid, "objetivo": "",
        "treinos": [treino or {"data": QUA, "tipo": "ACADEMIA", "duracao_min": 45,
                               "descricao": DESCRICAO}],
    }


class TestCheck:
    def test_marcar_itens_salva_sem_registrar(self, auth_client, fake_db, run):
        """Marcar exercício salva progresso, mas não fecha a sessão."""
        client, uid = auth_client
        run(fake_db.semanas.insert_one(_semana(uid)))

        r = client.post(f"/workout/treino/{SEG}/{QUA}/academia-execucao",
                        json={"itens_feitos": [0, 2], "sensacao": None})

        assert r.status_code == 200
        d = r.json()
        assert d["registrado"] is False
        assert d["execucao"]["itens_feitos"] == [0, 2]
        assert d["execucao"]["total_itens"] == 3

        doc = run(fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": uid}))
        assert doc["treinos"][0]["execucao"]["itens_feitos"] == [0, 2]
        assert doc["treinos"][0].get("resultado") is None

    def test_indices_fora_da_lista_sao_descartados(self, auth_client, fake_db, run):
        client, uid = auth_client
        run(fake_db.semanas.insert_one(_semana(uid)))

        r = client.post(f"/workout/treino/{SEG}/{QUA}/academia-execucao",
                        json={"itens_feitos": [0, 9, -1, 0], "sensacao": None})

        assert r.json()["execucao"]["itens_feitos"] == [0]


class TestSensacaoFinaliza:
    def test_sensacao_registra_a_sessao(self, auth_client, fake_db, run):
        client, uid = auth_client
        run(fake_db.semanas.insert_one(_semana(uid)))

        r = client.post(f"/workout/treino/{SEG}/{QUA}/academia-execucao",
                        json={"itens_feitos": [0, 1, 2], "sensacao": 5})

        assert r.status_code == 200
        d = r.json()
        assert d["registrado"] is True
        assert d["nota"] == 9.0

        doc = run(fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": uid}))
        t = doc["treinos"][0]
        assert t["descricao"] == DESCRICAO           # prescrição intacta
        assert t["execucao"]["sensacao"] == 5
        res = t["resultado"]
        assert res["origem"] == "relato_atleta"
        assert res["duracao_min"] == 45
        # O relato traz o que foi (e não foi) executado — é o que alimenta a IA.
        assert "3 de 3 exercícios" in res["relato"]
        assert "Agachamento — 3x10" in res["relato"]
        assert "5/5 (muito bem)" in res["relato"]

    def test_relato_lista_o_que_faltou(self, auth_client, fake_db, run):
        client, uid = auth_client
        run(fake_db.semanas.insert_one(_semana(uid)))

        client.post(f"/workout/treino/{SEG}/{QUA}/academia-execucao",
                    json={"itens_feitos": [0], "sensacao": 2})

        doc = run(fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": uid}))
        relato = doc["treinos"][0]["resultado"]["relato"]
        assert "1 de 3 exercícios" in relato
        assert "Não executados:" in relato
        assert "Panturrilha — 4x15" in relato
        assert "2/5 (ruim)" in relato

    def test_sensacao_invalida(self, auth_client, fake_db, run):
        client, uid = auth_client
        run(fake_db.semanas.insert_one(_semana(uid)))

        r = client.post(f"/workout/treino/{SEG}/{QUA}/academia-execucao",
                        json={"itens_feitos": [0], "sensacao": 9})
        assert r.status_code == 400


class TestRecusas:
    def test_treino_de_bike_recusado(self, auth_client, fake_db, run):
        client, uid = auth_client
        run(fake_db.semanas.insert_one(_semana(uid, {
            "data": QUA, "tipo": "TIROS", "duracao_min": 60, "descricao": "8x30s"})))

        r = client.post(f"/workout/treino/{SEG}/{QUA}/academia-execucao",
                        json={"itens_feitos": [0], "sensacao": 4})
        assert r.status_code == 400
        assert "academia" in r.json()["detail"].lower()

    def test_dia_que_ainda_nao_chegou(self, auth_client, fake_db, run):
        """O checklist abre no dia — marcar exercício de amanhã não faz sentido."""
        from datetime import timedelta
        from app.utils import hoje_local

        client, uid = auth_client
        amanha_d = hoje_local() + timedelta(days=1)
        amanha = amanha_d.isoformat()
        seg = (amanha_d - timedelta(days=amanha_d.weekday())).isoformat()
        run(fake_db.semanas.insert_one({
            "semana_inicio": seg, "user_id": uid, "objetivo": "",
            "treinos": [{"data": amanha, "tipo": "ACADEMIA", "duracao_min": 45,
                         "descricao": DESCRICAO}],
        }))

        r = client.post(f"/workout/treino/{seg}/{amanha}/academia-execucao",
                        json={"itens_feitos": [0], "sensacao": 4})
        assert r.status_code == 400
        assert "ainda não aconteceu" in r.json()["detail"]

    def test_descricao_sem_lista(self, auth_client, fake_db, run):
        client, uid = auth_client
        run(fake_db.semanas.insert_one(_semana(uid, {
            "data": QUA, "tipo": "ACADEMIA", "duracao_min": 40,
            "descricao": "Musculação livre, o que der na cabeça"})))

        r = client.post(f"/workout/treino/{SEG}/{QUA}/academia-execucao",
                        json={"itens_feitos": [0], "sensacao": 4})
        assert r.status_code == 400
        assert "lista de exercícios" in r.json()["detail"]


class TestCargas:
    def test_carga_salva_e_entra_no_relato(self, auth_client, fake_db, run):
        """O kg registrado é o que dá à IA um número real para progredir."""
        client, uid = auth_client
        run(fake_db.semanas.insert_one(_semana(uid)))

        client.post(f"/workout/treino/{SEG}/{QUA}/academia-execucao", json={
            "itens_feitos": [0, 1, 2],
            "cargas": {"0": 20, "1": 35.5, "2": 40},
            "sensacao": 4,
        })

        doc = run(fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": uid}))
        t = doc["treinos"][0]
        assert t["execucao"]["cargas"] == {"0": 20.0, "1": 35.5, "2": 40.0}
        relato = t["resultado"]["relato"]
        assert "Agachamento — 3x10 (20 kg)" in relato
        assert "Abdutor — 3x12 (35,5 kg)" in relato

    def test_carga_vazia_ou_zero_e_ignorada(self, auth_client, fake_db, run):
        """Campo em branco significa "não anotei", não "levantei 0 kg"."""
        client, uid = auth_client
        run(fake_db.semanas.insert_one(_semana(uid)))

        r = client.post(f"/workout/treino/{SEG}/{QUA}/academia-execucao", json={
            "itens_feitos": [0, 1], "cargas": {"0": 0, "1": 12, "9": 50}, "sensacao": None,
        })

        assert r.json()["execucao"]["cargas"] == {"1": 12.0}

    def test_carga_absurda_recusada(self, auth_client, fake_db, run):
        client, uid = auth_client
        run(fake_db.semanas.insert_one(_semana(uid)))

        r = client.post(f"/workout/treino/{SEG}/{QUA}/academia-execucao", json={
            "itens_feitos": [0], "cargas": {"0": 2000}, "sensacao": None,
        })
        assert r.status_code == 400
        assert "digitação" in r.json()["detail"]

    def test_sem_carga_relato_nao_inventa_kg(self, auth_client, fake_db, run):
        client, uid = auth_client
        run(fake_db.semanas.insert_one(_semana(uid)))

        client.post(f"/workout/treino/{SEG}/{QUA}/academia-execucao",
                    json={"itens_feitos": [0], "sensacao": 3})

        doc = run(fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": uid}))
        assert "kg" not in doc["treinos"][0]["resultado"]["relato"]


class TestSalvarSemanaPreserva:
    def test_salvar_semana_nao_apaga_execucao(self, auth_client, fake_db, run):
        """`execucao` não está no modelo TreinoSemana — sem preservação explícita
        o botão "Salvar Semana" apagaria os checks recém-dados."""
        client, uid = auth_client
        run(fake_db.semanas.insert_one(_semana(uid)))
        client.post(f"/workout/treino/{SEG}/{QUA}/academia-execucao",
                    json={"itens_feitos": [0, 1], "sensacao": None})

        r = client.post("/workout/semana", json={
            "semana_inicio": SEG, "objetivo": "",
            "treinos": [{"data": QUA, "tipo": "ACADEMIA", "duracao_min": 45,
                         "descricao": DESCRICAO}],
        })
        assert r.status_code == 200

        doc = run(fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": uid}))
        t = next(x for x in doc["treinos"] if x["data"] == QUA)
        assert t["execucao"]["itens_feitos"] == [0, 1]
