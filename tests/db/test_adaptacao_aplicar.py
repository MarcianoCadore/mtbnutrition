"""Aplicação do ajuste: grava a semana e refaz o agendamento no Garmin (peça 2).

INVARIANTE que estes testes travam: todo dia alterado tem o workout antigo
APAGADO no Garmin antes do novo subir. Sem isso o pull seguinte re-importa o
treino velho e o ajuste é desfeito sozinho — o mesmo bug que já aconteceu no
chat web ao mover treino.
"""
import pytest
from bson import ObjectId

from app.services import adaptacao_service as ad

# user_id real (ObjectId): é assim que o perfil — e as zonas do atleta — são
# encontrados pelo user_service.
UID_OID = ObjectId()
UID = str(UID_OID)
SEG = "2026-08-24"
QUI, SEX, DOM = "2026-08-27", "2026-08-28", "2026-08-30"


@pytest.fixture
def garmin_falso(monkeypatch):
    """Registra as chamadas ao Garmin em vez de bater na API."""
    chamadas = {"apagados": [], "subidos": []}

    async def _deletar(user_id, gid):
        chamadas["apagados"].append(gid)
        return True

    async def _upload(user_id, tipo, duracao_min, nome, data_iso, descricao=None,
                      forcar_indoor=None):
        chamadas["subidos"].append({"data": data_iso, "tipo": tipo,
                                    "duracao_min": duracao_min,
                                    "descricao": descricao,
                                    "indoor": forcar_indoor})
        return f"gid-novo-{data_iso}"

    import app.services.garmin_workout_service as gw
    monkeypatch.setattr(gw, "deletar_workout_garmin", _deletar)
    monkeypatch.setattr(gw, "upload_e_agendar", _upload)
    return chamadas


def _semana():
    return {
        "semana_inicio": SEG, "user_id": UID, "objetivo": "",
        "treinos": [
            {"data": QUI, "tipo": "Z2_LONGO", "duracao_min": 120, "descricao": "Base Z2",
             "resultado": {"tipo_realizado": "VO2MAX", "duracao_min": 50}},
            {"data": SEX, "tipo": "VO2MAX", "duracao_min": 75, "descricao": "5×4 min Z5",
             "periodo": "manha", "indoor": True, "garmin_workout_id": "gid-antigo-sexta"},
            {"data": DOM, "tipo": "RECUPERACAO", "duracao_min": 60, "descricao": "Leve"},
        ],
    }


def _proposta(ajustes, motivo_desvio="trocou_o_treino"):
    return {
        "desvio": {"data": QUI, "motivo": motivo_desvio},
        "ajustes": ajustes,
        "resumo": "Quinta virou forte — sexta alivia.",
    }


class TestGravaASemana:
    async def test_troca_o_treino_do_dia(self, fake_db, garmin_falso):
        await fake_db.semanas.insert_one(_semana())
        await ad.aplicar_ajustes(UID, SEG, _proposta([{
            "data": SEX, "tipo": "RECUPERACAO", "duracao_min": 60,
            "descricao": "Pedal leve Z1.", "cadencia_rpm": None,
            "motivo": "Quinta foi VO2máx de verdade.",
        }]))

        doc = await fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": UID})
        sexta = next(t for t in doc["treinos"] if t["data"] == SEX)
        assert sexta["tipo"] == "RECUPERACAO"
        assert sexta["duracao_min"] == 60
        assert "Pedal leve Z1." in sexta["descricao"]

    async def test_guarda_o_motivo_e_o_que_era_antes(self, fake_db, garmin_falso):
        """No modo automático o plano muda sozinho — o atleta precisa abrir o card
        e entender por quê."""
        await fake_db.semanas.insert_one(_semana())
        await ad.aplicar_ajustes(UID, SEG, _proposta([{
            "data": SEX, "tipo": "RECUPERACAO", "duracao_min": 60,
            "descricao": "Leve.", "motivo": "Quinta foi VO2máx de verdade.",
        }]))

        doc = await fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": UID})
        ajuste = next(t for t in doc["treinos"] if t["data"] == SEX)["ajuste_ia"]
        assert ajuste["motivo"] == "Quinta foi VO2máx de verdade."
        assert ajuste["antes"] == {"tipo": "VO2MAX", "duracao_min": 75}
        assert ajuste["desvio"]["data"] == QUI

    async def test_nao_mexe_na_rotina_do_atleta(self, fake_db, garmin_falso):
        """Período do dia e indoor são escolha dele, não do treinador."""
        await fake_db.semanas.insert_one(_semana())
        await ad.aplicar_ajustes(UID, SEG, _proposta([{
            "data": SEX, "tipo": "RECUPERACAO", "duracao_min": 60, "descricao": "Leve.",
        }]))

        doc = await fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": UID})
        sexta = next(t for t in doc["treinos"] if t["data"] == SEX)
        assert sexta["periodo"] == "manha" and sexta["indoor"] is True

    async def test_dia_que_vira_descanso_fica_limpo(self, fake_db, garmin_falso):
        await fake_db.semanas.insert_one(_semana())
        await ad.aplicar_ajustes(UID, SEG, _proposta([{
            "data": SEX, "tipo": "DESCANSO", "duracao_min": None, "descricao": "",
            "motivo": "Semana já teve carga demais.",
        }]))

        doc = await fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": UID})
        sexta = next(t for t in doc["treinos"] if t["data"] == SEX)
        assert (sexta["tipo"], sexta["duracao_min"], sexta["descricao"]) == ("DESCANSO", None, "")

    async def test_legenda_de_alvos_entra_na_descricao(self, fake_db, garmin_falso):
        """A descrição ajustada sai igual à de um dia gerado: o código anexa as
        faixas reais do atleta."""
        await fake_db.users.insert_one({
            "_id": UID_OID,
            "zonas": {"fc_max": 190, "limiar": 168, "zonas": [
                {"zona": 1, "min": 100, "max": 134}, {"zona": 2, "min": 135, "max": 153},
                {"zona": 3, "min": 154, "max": 164}, {"zona": 4, "min": 165, "max": 177},
                {"zona": 5, "min": 178, "max": 190}]},
        })
        await fake_db.semanas.insert_one(_semana())
        await ad.aplicar_ajustes(UID, SEG, _proposta([{
            "data": SEX, "tipo": "RECUPERACAO", "duracao_min": 60, "descricao": "Leve.",
        }]))

        doc = await fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": UID})
        sexta = next(t for t in doc["treinos"] if t["data"] == SEX)
        assert "Zona 1 100-134" in sexta["descricao"]


class TestGarmin:
    async def test_apaga_o_antigo_e_sobe_o_novo(self, fake_db, garmin_falso):
        await fake_db.semanas.insert_one(_semana())
        r = await ad.aplicar_ajustes(UID, SEG, _proposta([{
            "data": SEX, "tipo": "RECUPERACAO", "duracao_min": 60, "descricao": "Leve.",
        }]))

        assert garmin_falso["apagados"] == ["gid-antigo-sexta"]
        assert garmin_falso["subidos"][0]["tipo"] == "RECUPERACAO"
        assert r["garmin_ok"] is True

    async def test_guarda_o_id_novo_do_workout(self, fake_db, garmin_falso):
        await fake_db.semanas.insert_one(_semana())
        await ad.aplicar_ajustes(UID, SEG, _proposta([{
            "data": SEX, "tipo": "RECUPERACAO", "duracao_min": 60, "descricao": "Leve.",
        }]))

        doc = await fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": UID})
        sexta = next(t for t in doc["treinos"] if t["data"] == SEX)
        assert sexta["garmin_workout_id"] == f"gid-novo-{SEX}"

    async def test_descanso_apaga_e_nao_sobe_nada(self, fake_db, garmin_falso):
        await fake_db.semanas.insert_one(_semana())
        await ad.aplicar_ajustes(UID, SEG, _proposta([{
            "data": SEX, "tipo": "DESCANSO", "duracao_min": None, "descricao": "",
        }]))

        assert garmin_falso["apagados"] == ["gid-antigo-sexta"]
        assert garmin_falso["subidos"] == []

    async def test_respeita_o_indoor_do_dia(self, fake_db, garmin_falso):
        await fake_db.semanas.insert_one(_semana())
        await ad.aplicar_ajustes(UID, SEG, _proposta([{
            "data": SEX, "tipo": "TEMPO", "duracao_min": 70, "descricao": "3×10 Z3.",
        }]))
        assert garmin_falso["subidos"][0]["indoor"] is True

    async def test_falha_no_garmin_nao_derruba_a_gravacao(self, fake_db, monkeypatch,
                                                          garmin_falso):
        async def _upload_quebrado(*a, **kw):
            raise RuntimeError("Garmin fora do ar")

        import app.services.garmin_workout_service as gw
        monkeypatch.setattr(gw, "upload_e_agendar", _upload_quebrado)

        await fake_db.semanas.insert_one(_semana())
        r = await ad.aplicar_ajustes(UID, SEG, _proposta([{
            "data": SEX, "tipo": "RECUPERACAO", "duracao_min": 60, "descricao": "Leve.",
        }]))

        doc = await fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": UID})
        sexta = next(t for t in doc["treinos"] if t["data"] == SEX)
        assert sexta["tipo"] == "RECUPERACAO", "o plano do app vale mesmo sem o relógio"
        assert r["garmin_ok"] is False


class TestUmaAdaptacaoPorDesvio:
    async def test_segunda_tentativa_nao_passa(self, fake_db):
        """O sync roda a cada 10 min: o mesmo desvio não pode reescrever a semana
        de novo a cada rodada."""
        assert await ad.claim_adaptacao(UID, QUI) is True
        assert await ad.claim_adaptacao(UID, QUI) is False

    async def test_outro_dia_e_outro_desvio(self, fake_db):
        assert await ad.claim_adaptacao(UID, QUI) is True
        assert await ad.claim_adaptacao(UID, SEX) is True
