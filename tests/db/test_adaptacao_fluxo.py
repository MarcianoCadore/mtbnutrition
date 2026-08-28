"""Do desvio detectado até a semana ajustada (peça 3): gatilho, modo e aviso.

O atleta não avisa nada: quem dispara isto é o sync do Garmin (fez diferente) ou
o job noturno (não fez). Daí em diante o modo do perfil decide se a IA aplica
sozinha ou só propõe.
"""
import pytest
from bson import ObjectId

from app.services import adaptacao_service as ad

UID_OID = ObjectId()
UID = str(UID_OID)
SEG = "2026-08-24"
QUI, SEX, DOM = "2026-08-27", "2026-08-28", "2026-08-30"


@pytest.fixture
def semana(fake_db):
    async def _seed(modo="auto"):
        await fake_db.users.insert_one({
            "_id": UID_OID, "login": "atleta",
            "preferencias": {"adaptacao": modo, "dias_treino": [0, 1, 2, 3, 4, 5, 6]},
        })
        await fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": UID, "objetivo": "",
            "treinos": [
                {"data": QUI, "tipo": "Z2_LONGO", "duracao_min": 120, "descricao": "Base",
                 "resultado": {"tipo_realizado": "VO2MAX", "duracao_min": 50}},
                {"data": SEX, "tipo": "VO2MAX", "duracao_min": 75, "descricao": "5×4 Z5"},
                {"data": DOM, "tipo": "RECUPERACAO", "duracao_min": 60, "descricao": "Leve"},
            ],
        })
    return _seed


@pytest.fixture(autouse=True)
def sem_rede(monkeypatch):
    """IA, Garmin e WhatsApp fora do caminho — o que se testa aqui é o fluxo."""
    enviados = []

    async def _propor(user_id, semana_inicio, desvio, hoje=None):
        return {
            "desvio": desvio,
            "resumo": "Quinta virou forte — sexta alivia.",
            "ajustes": [{"data": SEX, "tipo": "RECUPERACAO", "duracao_min": 60,
                         "descricao": "Pedal leve Z1.", "cadencia_rpm": None,
                         "motivo": "Quinta foi VO2máx de verdade."}],
        }

    async def _deletar(user_id, gid):
        return True

    async def _upload(user_id, **kw):
        return "gid-novo"

    async def _send(to, msg):
        enviados.append(msg)

    async def _telefone(user_id):
        return "+5511999999999"

    import app.services.garmin_workout_service as gw
    import app.services.whatsapp_service as ws
    import app.services.user_service as us
    monkeypatch.setattr(ad, "propor_ajuste", _propor)
    monkeypatch.setattr(gw, "deletar_workout_garmin", _deletar)
    monkeypatch.setattr(gw, "upload_e_agendar", _upload)
    monkeypatch.setattr(ws, "send_message", _send)
    monkeypatch.setattr(us, "telefone_notificavel", _telefone)
    return enviados


class TestModoAutomatico:
    async def test_ajusta_a_semana_sozinho(self, fake_db, semana):
        await semana("auto")
        r = await ad.rodar_para_dia(UID, QUI, hoje=QUI)

        assert r["status"] == "aplicada"
        doc = await fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": UID})
        assert next(t for t in doc["treinos"] if t["data"] == SEX)["tipo"] == "RECUPERACAO"

    async def test_avisa_no_whatsapp_o_que_mudou(self, fake_db, semana, sem_rede):
        await semana("auto")
        await ad.rodar_para_dia(UID, QUI, hoje=QUI)

        assert len(sem_rede) == 1
        msg = sem_rede[0]
        assert "Ajustei a semana" in msg
        assert "VO2máx" in msg and "Recuperação" in msg
        assert "Quinta foi VO2máx de verdade." in msg

    async def test_mesmo_desvio_nao_reescreve_a_semana_de_novo(self, fake_db, semana):
        """O sync roda a cada 10 min — a segunda passada não faz nada."""
        await semana("auto")
        assert await ad.rodar_para_dia(UID, QUI, hoje=QUI) is not None
        assert await ad.rodar_para_dia(UID, QUI, hoje=QUI) is None


class TestModoAceite:
    async def test_nao_toca_na_semana_e_deixa_pendente(self, fake_db, semana):
        await semana("aceite")
        r = await ad.rodar_para_dia(UID, QUI, hoje=QUI)

        assert r["status"] == "pendente"
        doc = await fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": UID})
        assert next(t for t in doc["treinos"] if t["data"] == SEX)["tipo"] == "VO2MAX"
        assert (await ad.pendente(UID))["status"] == "pendente"

    async def test_aviso_pede_decisao(self, fake_db, semana, sem_rede):
        await semana("aceite")
        await ad.rodar_para_dia(UID, QUI, hoje=QUI)
        assert "Sugestão de ajuste" in sem_rede[0]

    async def test_ok_do_atleta_aplica(self, fake_db, semana):
        await semana("aceite")
        await ad.rodar_para_dia(UID, QUI, hoje=QUI)

        r = await ad.aplicar_pendente(UID, aceitar=True)
        assert r["status"] == "aplicada"
        doc = await fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": UID})
        assert next(t for t in doc["treinos"] if t["data"] == SEX)["tipo"] == "RECUPERACAO"
        assert await ad.pendente(UID) is None

    async def test_recusa_mantem_o_plano(self, fake_db, semana):
        await semana("aceite")
        await ad.rodar_para_dia(UID, QUI, hoje=QUI)

        assert (await ad.aplicar_pendente(UID, aceitar=False))["status"] == "recusada"
        doc = await fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": UID})
        assert next(t for t in doc["treinos"] if t["data"] == SEX)["tipo"] == "VO2MAX"


class TestQuandoNaoFazerNada:
    async def test_dia_que_seguiu_o_plano(self, fake_db, semana):
        await semana("auto")
        await fake_db.semanas.update_one(
            {"semana_inicio": SEG, "user_id": UID, "treinos.data": QUI},
            {"$set": {"treinos.$.resultado": {"tipo_realizado": "Z2_LONGO",
                                              "duracao_min": 115}}},
        )
        assert await ad.rodar_para_dia(UID, QUI, hoje=QUI) is None

    async def test_dia_sem_semana_no_banco(self, fake_db):
        assert await ad.rodar_para_dia(UID, QUI, hoje=QUI) is None


class TestModoDoPerfil:
    async def test_padrao_e_automatico(self, fake_db):
        await fake_db.users.insert_one({"_id": UID_OID, "login": "x"})
        assert await ad.modo_adaptacao(UID) == "auto"

    async def test_valor_invalido_cai_no_automatico(self, fake_db):
        await fake_db.users.insert_one({"_id": UID_OID, "login": "x",
                                        "preferencias": {"adaptacao": "sei_la"}})
        assert await ad.modo_adaptacao(UID) == "auto"

    async def test_salva_a_escolha(self, fake_db):
        await fake_db.users.insert_one({"_id": UID_OID, "login": "x"})
        assert await ad.definir_modo_adaptacao(UID, "aceite") == "aceite"
        assert await ad.modo_adaptacao(UID) == "aceite"


class TestAviso:
    def test_treino_nao_feito_abre_diferente(self):
        msg = ad.formatar_aviso({
            "desvio": {"data": QUI, "motivo": "nao_fez", "tipo_planejado": "VO2MAX"},
            "resumo": "", "ajustes": [{"data": SEX, "tipo": "TEMPO", "duracao_min": 90}],
        }, aplicado=True)
        assert "não aconteceu" in msg

    def test_falha_no_garmin_aparece_no_aviso(self):
        msg = ad.formatar_aviso({
            "desvio": {"data": QUI, "motivo": "nao_fez", "tipo_planejado": "VO2MAX"},
            "resumo": "", "ajustes": [{"data": SEX, "tipo": "TEMPO", "duracao_min": 90}],
        }, aplicado=True, garmin_ok=False)
        assert "Garmin" in msg and "⚠️" in msg
