"""Alvo duplo no Garmin: watts e FC no mesmo step.

O relógio aceita um alvo primário (o que dispara o alerta de "fora da zona") e um
secundário, exibido junto. Com os dois preenchidos o atleta abre o treino no Edge
e segue a métrica que tiver no dia — medidor no rolo, cinta na trilha — sem
precisar decidir na véspera qual versão mandar.

Regressão que motivou o arquivo: `_aplicar_bpm` apagava o `targetValue` (número da
zona) de que `_aplicar_watts` precisava, então as duas conversões nunca podiam
rodar sobre o mesmo workout. Agora uma única passada (`_aplicar_alvos`) lê a zona
e escreve as duas faixas.
"""
import pytest

from garminconnect.workout import TargetType

from app.services.garmin_workout_service import (
    _sem_secundario,
    _tem_secundario,
    build_cycling_workout,
)

# Zonas de um atleta qualquer — os números são só âncoras do teste, o app nunca
# embute faixa fixa (cada atleta tem as suas).
ZONAS_BPM = {1: {"min": 123, "max": 145}, 2: {"min": 146, "max": 158},
             3: {"min": 159, "max": 165}, 4: {"min": 166, "max": 177},
             5: {"min": 178, "max": 190}}
ZONAS_W = {1: {"min": 0, "max": 165}, 2: {"min": 168, "max": 225},
           3: {"min": 228, "max": 270}, 4: {"min": 273, "max": 315},
           5: {"min": 318, "max": 360}, 6: {"min": 363, "max": 450},
           7: {"min": 453, "max": 9999}}


def _steps(workout):
    """Todos os steps executáveis, com os repeat groups achatados."""
    plano = []

    def _walk(lst):
        for s in lst:
            filhos = getattr(s, "workoutSteps", None)
            _walk(filhos) if filhos else plano.append(s)

    for seg in workout.workoutSegments:
        _walk(seg.workoutSteps)
    return plano


def _build(**kw):
    return build_cycling_workout("VO2MAX", 62, "x", None, **kw)


class TestAlvoDuplo:
    def test_watts_primario_leva_fc_junto(self):
        w = _build(zonas_bpm=ZONAS_BPM, zonas_watts=ZONAS_W, primario="watts")
        for s in _steps(w):
            assert s.targetType["workoutTargetTypeId"] == TargetType.POWER
            assert s.secondaryTargetType["workoutTargetTypeId"] == TargetType.HEART_RATE

    def test_fc_primaria_leva_watts_junto(self):
        w = _build(zonas_bpm=ZONAS_BPM, zonas_watts=ZONAS_W, primario="fc")
        for s in _steps(w):
            assert s.targetType["workoutTargetTypeId"] == TargetType.HEART_RATE
            assert s.secondaryTargetType["workoutTargetTypeId"] == TargetType.POWER

    def test_as_duas_faixas_sao_as_do_atleta(self):
        """As faixas têm que ser as do atleta, não a zona genérica do aparelho —
        senão o alvo duplo mostraria dois números errados em vez de um."""
        w = _build(zonas_bpm=ZONAS_BPM, zonas_watts=ZONAS_W, primario="watts")
        # o miolo do VO2MAX é Z5
        z5 = [s for s in _steps(w) if s.targetValueOne == float(ZONAS_W[5]["min"])]
        assert z5, "nenhum step saiu com a faixa de watts da Z5"
        s = z5[0]
        assert s.targetValueTwo == float(ZONAS_W[5]["max"])
        assert (s.secondaryTargetValueOne, s.secondaryTargetValueTwo) == (
            float(ZONAS_BPM[5]["min"]), float(ZONAS_BPM[5]["max"]))

    def test_uma_metrica_so_nao_gera_secundario(self):
        """Quem escolheu 'só FC' não pode receber watts na tela do relógio."""
        w = _build(zonas_bpm=ZONAS_BPM)
        assert not _tem_secundario(w.workoutSegments[0].workoutSteps)
        for s in _steps(w):
            assert s.targetType["workoutTargetTypeId"] == TargetType.HEART_RATE

    def test_sem_ftp_cai_para_fc_mesmo_pedindo_watts(self):
        """Sem zonas de potência não há alvo de watts — o treino não pode sair sem
        alvo nenhum."""
        w = _build(zonas_bpm=ZONAS_BPM, primario="watts")
        for s in _steps(w):
            assert s.targetType["workoutTargetTypeId"] == TargetType.HEART_RATE
            assert s.targetValueOne is not None

    def test_zona_sem_faixa_de_fc_nao_vira_secundario_vazio(self):
        """A zona do próprio aparelho (heart.rate.zone) não tem min/max — mandá-la
        como secundária deixaria o campo do relógio em branco."""
        w = _build(zonas_bpm={}, zonas_watts=ZONAS_W, primario="watts")
        for s in _steps(w):
            assert s.targetType["workoutTargetTypeId"] == TargetType.POWER
            assert not hasattr(s, "secondaryTargetType")

    def test_z7_aberta_no_topo_vira_numero(self):
        """max=9999 é 'sem teto' na tabela de zonas; o relógio precisa de um número."""
        w = build_cycling_workout("TIROS", 62, "x", None,
                                  zonas_watts=ZONAS_W, primario="watts")
        for s in _steps(w):
            assert s.targetValueTwo < 9000

    def test_duracao_nao_muda_com_alvo_duplo(self):
        """O pull do Garmin regrava duracao_min a partir daqui — o alvo duplo não
        pode encostar nisso."""
        simples = _build(zonas_bpm=ZONAS_BPM)
        duplo = _build(zonas_bpm=ZONAS_BPM, zonas_watts=ZONAS_W, primario="watts")
        assert duplo.estimatedDurationInSecs == simples.estimatedDurationInSecs == 62 * 60


class TestFallback:
    def test_remover_secundario_preserva_o_primario(self):
        """Rede de segurança do upload: se o Garmin recusar o alvo duplo, o treino
        sobe com o primário em vez de o atleta ficar sem treino."""
        w = _build(zonas_bpm=ZONAS_BPM, zonas_watts=ZONAS_W, primario="watts")
        steps = w.workoutSegments[0].workoutSteps
        assert _tem_secundario(steps)

        _sem_secundario(steps)

        assert not _tem_secundario(steps)
        for s in _steps(w):
            assert s.targetType["workoutTargetTypeId"] == TargetType.POWER
            assert s.targetValueOne is not None

    def test_remover_entra_nos_repeat_groups(self):
        """VO2MAX guarda o miolo dentro de um repeat group — sobrou secundário lá
        dentro, o reenvio falha de novo."""
        w = _build(zonas_bpm=ZONAS_BPM, zonas_watts=ZONAS_W, primario="watts")
        grupos = [s for s in w.workoutSegments[0].workoutSteps
                  if getattr(s, "workoutSteps", None)]
        assert grupos, "VO2MAX deveria ter repeat group"

        _sem_secundario(w.workoutSegments[0].workoutSteps)

        for s in _steps(w):
            assert not hasattr(s, "secondaryTargetType")

    def test_json_enviado_carrega_os_campos_secundarios(self):
        """Os campos secundários são 'extra' do modelo pydantic — se caírem no
        model_dump, o Garmin nunca recebe o segundo alvo."""
        w = _build(zonas_bpm=ZONAS_BPM, zonas_watts=ZONAS_W, primario="watts")
        payload = w.to_dict()

        def _achatar(lst):
            for s in lst:
                if s.get("workoutSteps"):
                    yield from _achatar(s["workoutSteps"])
                else:
                    yield s

        steps = list(_achatar(payload["workoutSegments"][0]["workoutSteps"]))
        assert steps
        for s in steps:
            assert s["secondaryTargetType"]["workoutTargetTypeKey"] == "heart.rate"
            assert s["secondaryTargetValueOne"] and s["secondaryTargetValueTwo"]


@pytest.mark.asyncio
class TestModoAmbos:
    async def _usuario(self, fake_db, modo):
        from bson import ObjectId
        oid = ObjectId()
        await fake_db.users.insert_one({
            "_id": oid, "login": "a", "ftp": 300, "potencia_modo": modo,
            "zonas": {"fc_max": 190, "limiar": 172,
                      "zonas": [{"zona": z, **v} for z, v in ZONAS_BPM.items()]},
        })
        return str(oid)

    async def test_modo_ambos_e_aceito(self, fake_db):
        from app.services.config_service import salvar_ftp
        uid = await self._usuario(fake_db, "indoor")
        r = await salvar_ftp(uid, 300, "ambos")
        assert r["potencia_modo"] == "ambos"

    async def test_modo_invalido_ainda_cai_no_padrao(self, fake_db):
        from app.services.config_service import salvar_ftp
        uid = await self._usuario(fake_db, "indoor")
        r = await salvar_ftp(uid, 300, "watts-e-fc")
        assert r["potencia_modo"] == "indoor"


class _GarminFake:
    """Cliente Garmin de mentira: guarda o workout em vez de subir."""

    def __init__(self, recusa_duplo=False):
        self.recusa_duplo = recusa_duplo
        self.enviados = []

    def get_scheduled_workouts(self, ano, mes):
        return []

    def upload_cycling_workout(self, workout):
        payload = workout.to_dict()
        tem_duplo = any(
            "secondaryTargetType" in s
            for seg in payload["workoutSegments"]
            for s in seg["workoutSteps"]
        )
        if self.recusa_duplo and tem_duplo:
            raise RuntimeError("API Error 400 - secondary target não suportado")
        self.enviados.append(payload)
        return {"workoutId": "123"}

    def schedule_workout(self, wid, data):
        pass


@pytest.mark.asyncio
class TestUploadPorModo:
    """O modo do perfil decide o que chega no relógio — errar aqui manda o atleta
    treinar pela métrica que ele não tem no dia."""

    async def _usuario(self, fake_db, modo, ftp=300):
        from bson import ObjectId
        oid = ObjectId()
        doc = {"_id": oid, "login": "a", "potencia_modo": modo,
               "zonas": {"fc_max": 190, "limiar": 172,
                         "zonas": [{"zona": z, **v} for z, v in ZONAS_BPM.items()]}}
        if ftp:
            doc["ftp"] = ftp
        await fake_db.users.insert_one(doc)
        return str(oid)

    async def _enviar(self, monkeypatch, uid, tipo="VO2MAX", recusa_duplo=False, **kw):
        import app.services.garmin_service as gs
        from app.services.garmin_workout_service import upload_e_agendar

        api = _GarminFake(recusa_duplo=recusa_duplo)

        async def _fake_client(_user_id):
            return api

        monkeypatch.setattr(gs, "get_garmin_client", _fake_client)
        await upload_e_agendar(uid, tipo, 62, "x", "2026-08-24", **kw)
        return api.enviados[-1]

    def _primeiro_step(self, payload):
        return payload["workoutSegments"][0]["workoutSteps"][0]

    async def test_ambos_manda_as_duas_metricas(self, fake_db, monkeypatch):
        uid = await self._usuario(fake_db, "ambos")
        step = self._primeiro_step(await self._enviar(monkeypatch, uid))
        assert step["targetType"]["workoutTargetTypeKey"] == "power"
        assert step["secondaryTargetType"]["workoutTargetTypeKey"] == "heart.rate"

    async def test_ambos_respeita_o_toggle_outdoor_do_dia(self, fake_db, monkeypatch):
        """Marcou o dia como outdoor: a FC vira o alvo que apita, os watts ficam
        de referência."""
        uid = await self._usuario(fake_db, "ambos")
        step = self._primeiro_step(
            await self._enviar(monkeypatch, uid, forcar_indoor=False))
        assert step["targetType"]["workoutTargetTypeKey"] == "heart.rate"
        assert step["secondaryTargetType"]["workoutTargetTypeKey"] == "power"

    async def test_nunca_nao_manda_watts_nem_de_secundario(self, fake_db, monkeypatch):
        """'Nunca' é a resposta de quem não tem medidor — watts na tela seria ruído."""
        uid = await self._usuario(fake_db, "nunca")
        step = self._primeiro_step(await self._enviar(monkeypatch, uid))
        assert step["targetType"]["workoutTargetTypeKey"] == "heart.rate"
        assert "secondaryTargetType" not in step

    async def test_indoor_continua_so_watts_no_treino_de_qualidade(self, fake_db, monkeypatch):
        uid = await self._usuario(fake_db, "indoor")
        step = self._primeiro_step(await self._enviar(monkeypatch, uid))
        assert step["targetType"]["workoutTargetTypeKey"] == "power"
        assert "secondaryTargetType" not in step

    async def test_indoor_continua_so_fc_no_longao(self, fake_db, monkeypatch):
        uid = await self._usuario(fake_db, "indoor")
        step = self._primeiro_step(
            await self._enviar(monkeypatch, uid, tipo="Z2_LONGO"))
        assert step["targetType"]["workoutTargetTypeKey"] == "heart.rate"
        assert "secondaryTargetType" not in step

    async def test_toggle_indoor_do_dia_vence_o_modo_nunca(self, fake_db, monkeypatch):
        """'Nunca' é a preferência geral; marcar o dia como indoor é uma escolha
        explícita para aquela sessão e tem que valer."""
        uid = await self._usuario(fake_db, "nunca")
        step = self._primeiro_step(
            await self._enviar(monkeypatch, uid, forcar_indoor=True))
        assert step["targetType"]["workoutTargetTypeKey"] == "power"

    async def test_garmin_recusando_duplo_ainda_entrega_o_treino(self, fake_db, monkeypatch):
        """Se a API rejeitar o alvo secundário, reenvia só com o primário — o
        atleta não pode ficar com o dia vazio no relógio."""
        uid = await self._usuario(fake_db, "ambos")
        step = self._primeiro_step(
            await self._enviar(monkeypatch, uid, recusa_duplo=True))
        assert step["targetType"]["workoutTargetTypeKey"] == "power"
        assert "secondaryTargetType" not in step
