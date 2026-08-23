"""Regressão: dia de descanso virava treino de 0 min e sumia do Garmin.

Reportado em 2026-08-23 (semana de 24/08): a sexta era descanso, mas o card
mostrava "Tempo" e o treino nunca chegava no relógio. A descrição gerada pela IA
era "Descanso completo. Recuperação após TEMPO." — no scorer por palavras-chave
DESCANSO, RECUPERACAO e TEMPO empatam, e o desempate por intensidade
(_PRIORIDADE_TIPO) entrega TEMPO. O tipo era gravado a cada sync, mas
duracao_min continuava zerado, então o envio pro Garmin pulava o dia por não ter
duração: card de treino que nunca sincroniza.
"""
import pytest

SEG = "2026-08-24"
SEX = "2026-08-28"

pytestmark = pytest.mark.asyncio


class TestReclassificarNaoMexeEmDescanso:
    async def _rodar(self, fake_db, treinos, uid="u1"):
        from app.routes.workout import _reclassificar_impl
        await fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": uid, "objetivo": "", "treinos": treinos,
        })
        res = await _reclassificar_impl(uid, SEG)
        doc = await fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": uid})
        return res, {t["data"]: t for t in doc["treinos"]}

    async def test_caso_reportado_sexta_continua_descanso(self, fake_db):
        # O texto sozinho classifica como TEMPO — é o empate desempatado por
        # intensidade. O dia não tem duração, então não há sessão para classificar.
        from app.services.ai_service import classificar_por_texto
        desc = "Descanso completo. Recuperação após TEMPO."
        assert classificar_por_texto(desc) == "TEMPO"

        res, dias = await self._rodar(fake_db, [
            {"data": SEX, "tipo": "DESCANSO", "duracao_min": None, "descricao": desc},
        ])
        assert dias[SEX]["tipo"] == "DESCANSO"
        assert res["reclassificados"] == 0

    async def test_dia_sem_duracao_nao_e_reclassificado(self, fake_db):
        # Mesma proteção pela duração: sem sessão, não há o que classificar —
        # um tipo de bike aqui vira card que o envio pro Garmin pula.
        _, dias = await self._rodar(fake_db, [
            {"data": SEX, "tipo": "DESCANSO", "duracao_min": 0,
             "descricao": "Descanso completo. Recuperação após TEMPO."},
        ])
        assert dias[SEX]["tipo"] == "DESCANSO"

    async def test_dia_ja_carimbado_volta_a_ser_descanso(self, fake_db):
        # Estado exato do banco do caso reportado: TEMPO com duração 0 e sem
        # workout no Garmin. Não é sessão nenhuma — o sync desfaz o carimbo.
        res, dias = await self._rodar(fake_db, [
            {"data": SEX, "tipo": "TEMPO", "duracao_min": 0,
             "garmin_workout_id": None,
             "descricao": "Descanso completo. Recuperação após TEMPO."},
        ])
        assert dias[SEX]["tipo"] == "DESCANSO"
        assert dias[SEX]["duracao_min"] is None
        assert res["reclassificados"] == 1

    async def test_treino_importado_do_garmin_sem_duracao_nao_vira_descanso(self, fake_db):
        # Veio do Garmin (tem gid) mas a API não devolveu a duração: é sessão de
        # verdade, não pode virar descanso.
        _, dias = await self._rodar(fake_db, [
            {"data": SEX, "tipo": "TEMPO", "duracao_min": None,
             "garmin_workout_id": "999",
             "descricao": "3×15 min em Z3/Z4 com 5 min Z1 entre cada."},
        ])
        assert dias[SEX]["tipo"] == "TEMPO"

    async def test_academia_sem_duracao_nao_vira_descanso(self, fake_db):
        # ACADEMIA nunca vai pro Garmin, então nunca tem gid — a regra do gid
        # não pode transformá-la em descanso.
        _, dias = await self._rodar(fake_db, [
            {"data": SEX, "tipo": "ACADEMIA", "duracao_min": None,
             "descricao": "ACADEMIA — Força MTB (foco: pernas+core)"},
        ])
        assert dias[SEX]["tipo"] == "ACADEMIA"

    async def test_treino_de_verdade_continua_sendo_reclassificado(self, fake_db):
        # A proteção não pode desligar a reclassificação: um dia com duração e
        # descrição de VO2máx tem que sair de RECUPERACAO.
        res, dias = await self._rodar(fake_db, [
            {"data": SEG, "tipo": "RECUPERACAO", "duracao_min": 75,
             "descricao": "15 min aquecimento. 5×4 min Z5 com 4 min Z2. 10 min soltura."},
        ])
        assert dias[SEG]["tipo"] == "VO2MAX"
        assert res["reclassificados"] == 1
