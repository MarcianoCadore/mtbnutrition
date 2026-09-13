"""Aba velha não desfaz o que aconteceu enquanto ela estava aberta.

Em 31/08/2026 o atleta ficou com o calendário aberto por horas. Nesse meio-tempo
o treino do dia foi corrigido de RECUPERACAO para VO2MAX no servidor. Quando ele
clicou em "Enviar + Sincronizar Garmin", a tela mandou o plano que tinha em
memória — o velho — e rebaixou o treino de volta, em silêncio, depois de já ter
sido avaliado.

Duas travas, uma por camada:
- a semana carrega um carimbo de versão que volta no salvamento (409 se mudou);
- dia com resultado é intocável por esta rota, venha o payload de onde vier.
"""
from datetime import date, timedelta

import pytest

# Datas RELATIVAS a hoje, de propósito. Na primeira versão deste arquivo elas
# eram fixas (31/08 a 02/09 de 2026) e, quando o calendário passou por elas, o
# teste do "dia futuro" parou de testar o dia futuro: a condição virou passado,
# a trava deixou de ser exercitada e o teste passou a falhar sozinho, sem que
# nada no produto tivesse quebrado. Teste com data fixa tem prazo de validade.
_HOJE = date.today()
SEG = (_HOJE + timedelta(days=(7 - _HOJE.weekday()))).isoformat()   # próxima segunda
TER = (date.fromisoformat(SEG) + timedelta(days=1)).isoformat()
QUA = (date.fromisoformat(SEG) + timedelta(days=2)).isoformat()


def _treino(data, tipo="Z2_LONGO", **extra):
    return {"data": data, "tipo": tipo, "duracao_min": 60,
            "descricao": f"{tipo} planejado", **extra}


def _payload(treinos, versao=None):
    corpo = {"semana_inicio": SEG, "objetivo": "", "treinos": treinos}
    if versao is not None:
        corpo["base_versao"] = versao
    return corpo


class TestVersaoDaSemana:
    def test_get_devolve_a_versao(self, auth_client, fake_db, run):
        client, uid = auth_client
        run(fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": uid, "objetivo": "",
            "treinos": [_treino(QUA)], "atualizado_em": "2026-08-31T20:00:00+00:00",
        }))

        d = client.get(f"/workout/semana/{SEG}").json()
        assert d["versao"] == "2026-08-31T20:00:00+00:00"

    def test_semana_nova_tem_versao_vazia(self, auth_client, fake_db):
        client, uid = auth_client
        assert client.get(f"/workout/semana/{SEG}").json()["versao"] == ""

    def test_salvar_com_a_versao_certa_passa(self, auth_client, fake_db, run):
        client, uid = auth_client
        run(fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": uid, "objetivo": "",
            "treinos": [_treino(QUA)], "atualizado_em": "v1",
        }))

        r = client.post("/workout/semana", json=_payload([_treino(QUA, "TIROS")], "v1"))

        assert r.status_code == 200
        assert r.json()["versao"] != "v1", "cada salvamento carimba uma versão nova"

    def test_salvar_com_versao_velha_e_recusado(self, auth_client, fake_db, run):
        """É o caso do 31/08: a aba tinha 'v1', o servidor já estava em 'v2'."""
        client, uid = auth_client
        run(fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": uid, "objetivo": "",
            "treinos": [_treino(QUA, "VO2MAX")], "atualizado_em": "v2",
        }))

        r = client.post("/workout/semana",
                        json=_payload([_treino(QUA, "RECUPERACAO")], "v1"))

        assert r.status_code == 409
        assert "Recarregue" in r.json()["detail"]

        doc = run(fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": uid}))
        assert doc["treinos"][0]["tipo"] == "VO2MAX", "nada pode ter sido gravado"

    def test_sem_versao_no_payload_continua_salvando(self, auth_client, fake_db, run):
        """O WhatsApp e as chamadas internas não têm tela — não mandam versão."""
        client, uid = auth_client
        run(fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": uid, "objetivo": "",
            "treinos": [_treino(QUA)], "atualizado_em": "v9",
        }))

        assert client.post("/workout/semana",
                           json=_payload([_treino(QUA, "TIROS")])).status_code == 200


class TestDiaJaRealizado:
    def test_dia_com_resultado_nao_e_reescrito(self, auth_client, fake_db, run):
        """O plano de um dia que já aconteceu virou histórico: é contra ele que a
        avaliação do treino foi feita."""
        client, uid = auth_client
        run(fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": uid, "objetivo": "",
            "treinos": [_treino(SEG, "VO2MAX", resultado={"duracao_min": 66})],
        }))

        r = client.post("/workout/semana",
                        json=_payload([_treino(SEG, "RECUPERACAO")]))

        assert r.status_code == 200
        doc = run(fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": uid}))
        t = doc["treinos"][0]
        assert t["tipo"] == "VO2MAX"
        assert t["descricao"] == "VO2MAX planejado"
        assert t["resultado"]["duracao_min"] == 66

    def test_dia_futuro_sem_resultado_continua_protegido(self, auth_client, fake_db, run):
        """Regra que já existia: só a IA reescreve o plano do que ainda vai vir."""
        client, uid = auth_client
        run(fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": uid, "objetivo": "",
            "treinos": [_treino(QUA, "TEMPO")],
        }))

        client.post("/workout/semana", json=_payload([_treino(QUA, "RECUPERACAO")]))

        doc = run(fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": uid}))
        assert doc["treinos"][0]["tipo"] == "TEMPO"
