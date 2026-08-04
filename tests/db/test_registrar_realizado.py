"""Registro de treino realizado a partir do relato do atleta.

Sessões que nenhum dispositivo captura (academia, pedal sem relógio) só podiam
entrar no sistema pelo chat, que usava `criar_treino_dia` para isso — reescrevia
a `descricao` do dia (apagando a prescrição planejada) e não gravava nada em
`resultado`. Estes testes travam o contrato inverso: `registrar_realizado`
escreve SÓ em `resultado` e nunca encosta no planejado.
"""
import pytest

from app.services import avaliacao_service as av

UID = "user-relato"
SEG = "2026-06-22"  # segunda
QUA = "2026-06-24"  # quarta


@pytest.fixture(autouse=True)
def _sem_ia(monkeypatch):
    """A análise pós-treino chama a API — devolve um veredito fixo."""
    import app.services.ai_service as ai

    async def _fake(planejado, resultado, user_id=None, fit_path=None, ignorar_fc=None):
        return {"nota": 8, "resumo": "ok", "pontos_fortes": [], "pontos_fracos": []}

    monkeypatch.setattr(ai, "analisar_atividade_pos_treino", _fake)


def _semana(treinos):
    return {"semana_inicio": SEG, "user_id": UID, "objetivo": "", "treinos": treinos}


class TestPreservaOPlanejado:
    async def test_nao_toca_no_treino_planejado(self, fake_db):
        """A regressão que motivou a ferramenta: o plano do dia sobrevive."""
        await fake_db.semanas.insert_one(_semana([{
            "data": QUA, "tipo": "ACADEMIA", "duracao_min": 40,
            "descricao": "Agachamento 4x8, supino 3x10, remada 3x12",
        }]))

        await av.registrar_realizado(
            UID, QUA, duracao_min=40, relato="Fiz tudo, me senti bem",
        )

        doc = await fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": UID})
        t = doc["treinos"][0]
        assert t["tipo"] == "ACADEMIA"
        assert t["duracao_min"] == 40
        assert t["descricao"] == "Agachamento 4x8, supino 3x10, remada 3x12"

    async def test_preserva_sub_bloco_de_academia(self, fake_db):
        await fake_db.semanas.insert_one(_semana([{
            "data": QUA, "tipo": "Z2_LONGO", "duracao_min": 90, "descricao": "Base Z2",
            "academia": {"duracao_min": 45, "descricao": "Core + posterior"},
        }]))

        await av.registrar_realizado(UID, QUA, duracao_min=95, relato="Pedal tranquilo")

        doc = await fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": UID})
        assert doc["treinos"][0]["academia"] == {
            "duracao_min": 45, "descricao": "Core + posterior",
        }

    async def test_ignora_extra_da_mesma_data(self, fake_db):
        """O extra vem primeiro no array — o resultado tem de cair no primário."""
        await fake_db.semanas.insert_one(_semana([
            {"data": QUA, "tipo": "ACADEMIA", "duracao_min": 50,
             "origem": "extra", "id": "extra-1"},
            {"data": QUA, "tipo": "TIROS", "duracao_min": 60, "descricao": "8x30s"},
        ]))

        r = await av.registrar_realizado(UID, QUA, duracao_min=60, relato="Fiz os tiros")

        assert r["tipo"] == "TIROS"
        doc = await fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": UID})
        extra = next(t for t in doc["treinos"] if t.get("origem") == "extra")
        primario = next(t for t in doc["treinos"] if t.get("origem") != "extra")
        assert extra.get("resultado") is None
        assert primario["resultado"]["duracao_min"] == 60


class TestConteudoDoResultado:
    async def test_marca_origem_e_fc_invalida(self, fake_db):
        """Sem dispositivo não há FC: a análise não pode cobrar zona nenhuma."""
        await fake_db.semanas.insert_one(_semana([
            {"data": QUA, "tipo": "ACADEMIA", "duracao_min": 40, "descricao": "Full body"},
        ]))

        await av.registrar_realizado(UID, QUA, duracao_min=40, relato="Tudo certo")

        doc = await fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": UID})
        res = doc["treinos"][0]["resultado"]
        assert res["origem"] == av.ORIGEM_RELATO
        assert res["fc_invalida"] is True
        assert res["fc_invalida_motivo"] == av.MOTIVO_SEM_DISPOSITIVO
        assert res["relato"] == "Tudo certo"
        assert res["analise_ia"]["nota"] == 8
        # Sem potência nem FC não dá para calcular TSS — o card cai no previsto.
        assert "tss_obtido" not in res

    async def test_herda_duracao_do_planejado(self, fake_db):
        await fake_db.semanas.insert_one(_semana([
            {"data": QUA, "tipo": "ACADEMIA", "duracao_min": 45, "descricao": "Full body"},
        ]))

        r = await av.registrar_realizado(UID, QUA, relato="Feito")

        assert r["duracao_min"] == 45

    async def test_campos_opcionais(self, fake_db):
        await fake_db.semanas.insert_one(_semana([
            {"data": QUA, "tipo": "Z2_LONGO", "duracao_min": 90, "descricao": "Base"},
        ]))

        await av.registrar_realizado(
            UID, QUA, duracao_min=95, relato="Pedal", distancia_km=42.5,
            percepcao_esforco=6,
        )

        doc = await fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": UID})
        res = doc["treinos"][0]["resultado"]
        assert res["distancia_km"] == 42.5
        assert res["percepcao_esforco"] == 6


class TestRecusas:
    async def test_semana_inexistente(self, fake_db):
        with pytest.raises(ValueError, match="semana"):
            await av.registrar_realizado(UID, QUA, duracao_min=40, relato="x")

    async def test_dia_de_descanso(self, fake_db):
        await fake_db.semanas.insert_one(_semana([
            {"data": QUA, "tipo": "DESCANSO", "duracao_min": None},
        ]))
        with pytest.raises(ValueError, match="não tem treino planejado"):
            await av.registrar_realizado(UID, QUA, duracao_min=40, relato="x")

    async def test_nao_sobrescreve_dado_do_garmin(self, fake_db):
        """Dado medido vale mais que memória — e o re-sync o traria de volta."""
        await fake_db.semanas.insert_one(_semana([{
            "data": QUA, "tipo": "TIROS", "duracao_min": 60, "descricao": "8x30s",
            "resultado": {"garmin_activity_id": 999, "duracao_min": 62, "avg_hr": 155},
        }]))

        with pytest.raises(ValueError, match="sincronizado"):
            await av.registrar_realizado(UID, QUA, duracao_min=60, relato="x")

        doc = await fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": UID})
        assert doc["treinos"][0]["resultado"]["avg_hr"] == 155

    async def test_data_futura(self, fake_db):
        """Não existe "já fiz" o treino de amanhã."""
        from datetime import timedelta
        from app.utils import hoje_local

        amanha = (hoje_local() + timedelta(days=1)).isoformat()
        seg = (hoje_local() + timedelta(days=1))
        seg = (seg - timedelta(days=seg.weekday())).isoformat()
        await fake_db.semanas.insert_one({
            "semana_inicio": seg, "user_id": UID, "objetivo": "",
            "treinos": [{"data": amanha, "tipo": "ACADEMIA", "duracao_min": 40,
                         "descricao": "Full body"}],
        })

        with pytest.raises(ValueError, match="ainda não chegou"):
            await av.registrar_realizado(UID, amanha, duracao_min=40, relato="x")

    async def test_sem_duracao_em_lugar_nenhum(self, fake_db):
        await fake_db.semanas.insert_one(_semana([
            {"data": QUA, "tipo": "ACADEMIA", "duracao_min": None, "descricao": "Full body"},
        ]))
        with pytest.raises(ValueError, match="duração"):
            await av.registrar_realizado(UID, QUA, relato="Feito")
