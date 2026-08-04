"""WhatsApp: 'a cinta estava sem bateria' refaz a avaliação do treino sem FC."""
from bson import ObjectId

SEG = "2026-06-22"
TER = "2026-06-23"
FONE = "+5551999990001"


def _seed(run, fake_db, user_id):
    run(fake_db.users.insert_one({"_id": ObjectId(user_id), "login": "x", "telefone": FONE}))
    run(fake_db.semanas.insert_one({
        "semana_inicio": SEG, "user_id": user_id, "objetivo": "",
        "treinos": [{
            "data": TER, "tipo": "TIROS", "duracao_min": 60,
            "resultado": {
                "duracao_min": 58, "avg_hr": 118, "max_hr": 131, "tss_obtido": 40,
                "analise_ia": {"nota": 4.0, "resumo": "faltou intensidade",
                               "pontos_fortes": [], "pontos_fracos": ["FC baixa"]},
            },
        }],
    }))


def _mock_ia(monkeypatch, data_iso):
    """Classificador de intenção e análise pós-treino, ambos determinísticos."""
    import app.services.ai_service as ai

    async def _interpretar(texto, referencia_datas):
        return {"intencao": "fc_invalida", "data": data_iso,
                "descricao": "cinta sem bateria"}

    async def _analisar(planejado, resultado, user_id=None, fit_path=None, ignorar_fc=None):
        assert ignorar_fc is True
        return {"nota": 8.0, "resumo": "Volume cumprido, sem dados de FC.",
                "pontos_fortes": [], "pontos_fracos": []}

    monkeypatch.setattr(ai, "interpretar_mensagem", _interpretar)
    monkeypatch.setattr(ai, "analisar_atividade_pos_treino", _analisar)


class TestWebhookFCInvalida:
    def test_reavalia_e_responde_com_nova_nota(self, client, fake_db, run, monkeypatch):
        user_id = str(ObjectId())
        _seed(run, fake_db, user_id)
        _mock_ia(monkeypatch, TER)

        r = client.post("/whatsapp/webhook", data={
            "Body": "a cinta cardíaca estava sem bateria nesse treino, ignora a FC",
            "From": f"whatsapp:{FONE}", "NumMedia": "0",
        })
        assert r.status_code == 200
        assert "sem considerar a FC" in r.text
        assert "8.0/10" in r.text

        doc = run(fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": user_id}))
        res = doc["treinos"][0]["resultado"]
        assert res["fc_invalida"] is True
        assert res["fc_invalida_motivo"] == "cinta sem bateria"
        assert res["analise_ia"]["nota"] == 8.0

    def test_dia_sem_resultado_responde_erro_amigavel(self, client, fake_db, run, monkeypatch):
        user_id = str(ObjectId())
        run(fake_db.users.insert_one({"_id": ObjectId(user_id), "login": "x", "telefone": FONE}))
        run(fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": user_id, "objetivo": "",
            "treinos": [{"data": TER, "tipo": "TIROS", "duracao_min": 60}],
        }))
        _mock_ia(monkeypatch, TER)

        r = client.post("/whatsapp/webhook", data={
            "Body": "esqueci a cinta cardíaca nesse treino",
            "From": f"whatsapp:{FONE}", "NumMedia": "0",
        })
        assert r.status_code == 200
        assert "não tem resultado sincronizado" in r.text
