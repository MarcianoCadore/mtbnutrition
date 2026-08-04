"""Dia duplo: bike + academia no mesmo dia, dois cards na mesma coluna.

Existem momentos da periodização que pedem duas sessões no dia (força de manhã,
pedal leve à noite). A musculação vai no sub-objeto `academia` do treino de
bike, e a execução dela é gravada dentro desse sub-objeto — o `resultado` do dia
pertence ao PEDAL, que ainda vai chegar pelo Garmin.
"""
import pytest

SEG = "2026-06-22"  # segunda
QUA = "2026-06-24"  # quarta

DESCRICAO_AC = """ACADEMIA — Força MTB (foco: superior+core)

POR QUE HOJE: pedal leve à noite, então a musculação não disputa as pernas.

EXERCÍCIOS:
1. Remada — 3x10 — 30 kg
2. Prancha — 3x45s — peso corporal

OBSERVAÇÕES:
- Descanso 90s"""


def _semana_dia_duplo(uid, tipo_bike="RECUPERACAO", dur_bike=50):
    return {
        "semana_inicio": SEG, "user_id": uid, "objetivo": "",
        "treinos": [{
            "data": QUA, "tipo": tipo_bike, "duracao_min": dur_bike,
            "descricao": "Pedal leve Z1", "periodo": "noite",
            "academia": {"duracao_min": 45, "periodo": "manha", "descricao": DESCRICAO_AC},
        }],
    }


class TestExecucaoNoSubObjeto:
    def test_checklist_grava_dentro_da_academia(self, auth_client, fake_db, run):
        client, uid = auth_client
        run(fake_db.semanas.insert_one(_semana_dia_duplo(uid)))

        r = client.post(f"/workout/treino/{SEG}/{QUA}/academia-execucao", json={
            "itens_feitos": [0, 1], "cargas": {"0": 32.5}, "sensacao": 4,
        })

        assert r.status_code == 200
        d = r.json()
        assert d["dia_duplo"] is True
        # O slot de resultado é do pedal: a academia não o consome.
        assert d["registrado"] is False

        doc = run(fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": uid}))
        t = doc["treinos"][0]
        assert t.get("resultado") is None
        assert t.get("execucao") is None
        exe = t["academia"]["execucao"]
        assert exe["itens_feitos"] == [0, 1]
        assert exe["cargas"] == {"0": 32.5}
        assert exe["sensacao"] == 4
        assert exe["total_itens"] == 2
        # A prescrição do pedal e a da academia continuam intactas.
        assert t["descricao"] == "Pedal leve Z1"
        assert t["academia"]["descricao"] == DESCRICAO_AC

    def test_exercicios_vem_do_sub_objeto(self, auth_client, fake_db, run):
        """A lista marcada é a da academia, não a descrição do pedal."""
        client, uid = auth_client
        run(fake_db.semanas.insert_one(_semana_dia_duplo(uid)))

        r = client.post(f"/workout/treino/{SEG}/{QUA}/academia-execucao",
                        json={"itens_feitos": [0, 1, 2], "sensacao": None})

        assert r.json()["execucao"]["total_itens"] == 2   # só 2 exercícios existem
        assert r.json()["execucao"]["itens_feitos"] == [0, 1]

    def test_bike_sem_academia_continua_recusando(self, auth_client, fake_db, run):
        client, uid = auth_client
        run(fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": uid, "objetivo": "",
            "treinos": [{"data": QUA, "tipo": "TIROS", "duracao_min": 60}],
        }))

        r = client.post(f"/workout/treino/{SEG}/{QUA}/academia-execucao",
                        json={"itens_feitos": [0], "sensacao": 4})
        assert r.status_code == 400


class TestGeradorSoDobraComPedalLeve:
    """A trava do dia duplo fica no código, não só no prompt — a IA desobedece."""

    def _normalizar(self, tipo, duracao):
        from app.services.plano_semana_service import (
            _TIPOS_ACEITAM_ACADEMIA, _DUPLO_MAX_MIN_BIKE,
        )
        return tipo in _TIPOS_ACEITAM_ACADEMIA and duracao <= _DUPLO_MAX_MIN_BIKE

    @pytest.mark.parametrize("tipo,dur,esperado", [
        ("RECUPERACAO", 50, True),
        ("Z2_LONGO", 120, True),
        ("Z2_LONGO", 210, False),   # longão: proibido dobrar
        ("VO2MAX", 62, False),
        ("TIROS", 65, False),
        ("TEMPO", 80, False),
        ("FORCA", 90, False),
    ])
    def test_combinacoes_permitidas(self, tipo, dur, esperado):
        assert self._normalizar(tipo, dur) is esperado
