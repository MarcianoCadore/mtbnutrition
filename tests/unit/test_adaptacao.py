"""Adaptação da semana quando o treino sai do plano (peça 1: detectar + validar).

Caso que originou tudo: o atleta fez um treino curto e forte porque não daria
para fazer o que estava prescrito. O app precisa entender o que ele fez e
arrumar os dias seguintes — sem repor volume e sem emendar dois dias duros.
"""
import pytest

from app.services.adaptacao_service import (
    classe_do_tipo,
    desvios_da_semana,
    detectar_desvio,
    validar_ajustes,
)

HOJE = "2026-08-27"          # quinta
SEXTA, SABADO, DOMINGO = "2026-08-28", "2026-08-29", "2026-08-30"


def dia(data, tipo, duracao=None, resultado=None, **extra):
    d = {"data": data, "tipo": tipo, "duracao_min": duracao, **extra}
    if resultado is not None:
        d["resultado"] = resultado
    return d


def feito(tipo, duracao, **extra):
    return {"tipo_realizado": tipo, "duracao_min": duracao, **extra}


class TestDetectarDesvio:
    def test_treino_curto_e_forte_no_lugar_do_longao(self):
        d = detectar_desvio(
            dia(HOJE, "Z2_LONGO", 120, feito("VO2MAX", 50)), hoje=HOJE)
        assert d["motivo"] == "trocou_o_treino"
        assert (d["classe_planejada"], d["classe_realizada"]) == ("facil", "duro")

    def test_seguiu_o_plano_nao_e_desvio(self):
        assert detectar_desvio(
            dia(HOJE, "VO2MAX", 75, feito("VO2MAX", 72)), hoje=HOJE) is None

    def test_vo2max_lido_como_tiros_nao_dispara_nada(self):
        """O classificador do .fit troca VO2máx por tiros (os dois são Z5). Como a
        comparação é por CLASSE de carga, isso não vira desvio."""
        assert detectar_desvio(
            dia(HOJE, "VO2MAX", 75, feito("TIROS", 74)), hoje=HOJE) is None

    def test_meia_hora_a_menos_num_longao_e_a_vida_real(self):
        assert detectar_desvio(
            dia(HOJE, "Z2_LONGO", 120, feito("Z2_LONGO", 105)), hoje=HOJE) is None

    def test_metade_do_treino_e_desvio_de_volume(self):
        d = detectar_desvio(dia(HOJE, "Z2_LONGO", 120, feito("Z2_LONGO", 60)), hoje=HOJE)
        assert d["motivo"] == "trocou_volume"

    def test_dia_futuro_nunca_e_desvio(self):
        assert detectar_desvio(dia(SEXTA, "VO2MAX", 75), hoje=HOJE) is None

    def test_hoje_sem_resultado_ainda_da_tempo(self):
        assert detectar_desvio(dia(HOJE, "VO2MAX", 75), hoje=HOJE) is None

    def test_dia_fechado_sem_resultado_e_treino_nao_feito(self):
        d = detectar_desvio(dia("2026-08-26", "VO2MAX", 75), hoje=HOJE)
        assert d["motivo"] == "nao_fez" and d["classe_realizada"] == "nenhum"

    def test_descanso_vazio_nao_e_desvio(self):
        assert detectar_desvio(dia("2026-08-26", "DESCANSO"), hoje=HOJE) is None

    def test_desvios_da_semana_ignora_treino_extra(self):
        treinos = [
            dia("2026-08-26", "Z2_LONGO", 120, feito("VO2MAX", 50)),
            dia("2026-08-26", "TIROS", 40, feito("TIROS", 40), origem="extra"),
        ]
        assert [d["data"] for d in desvios_da_semana(treinos, hoje=HOJE)] == ["2026-08-26"]


class TestValidador:
    """A IA propõe; estas regras não passam por ela."""

    # Atleta que treina todos os dias — assim as regras de agenda não interferem
    # nos casos abaixo (o dia sem treino tem teste próprio).
    PREF = {"dias_treino": [0, 1, 2, 3, 4, 5, 6]}

    def semana(self):
        return [
            dia(HOJE, "Z2_LONGO", 120, feito("VO2MAX", 50)),   # o desvio
            dia(SEXTA, "VO2MAX", 75),
            dia(SABADO, "Z2_LONGO", 180),
            dia(DOMINGO, "RECUPERACAO", 60),
        ]

    def test_dia_ja_treinado_nao_se_replaneja(self):
        ajustes = validar_ajustes(
            [{"data": HOJE, "tipo": "RECUPERACAO", "duracao_min": 60}],
            self.semana(), hoje=HOJE)
        assert ajustes == []

    def test_hoje_ainda_e_ajustavel_antes_de_treinar(self):
        """O desvio de ONTEM detectado às 5h: o treino de hoje ainda não aconteceu
        e é exatamente ele que deveria aliviar."""
        semana = [
            dia("2026-08-26", "VO2MAX", 75, feito("VO2MAX", 74)),   # ontem, duro
            dia(HOJE, "TEMPO", 100),                                 # hoje, ainda a fazer
            dia(SEXTA, "Z2_LONGO", 120),
        ]
        ajustes = validar_ajustes(
            [{"data": HOJE, "tipo": "RECUPERACAO", "duracao_min": 60,
              "descricao": "Leve.", "motivo": "Ontem foi VO2máx."}],
            semana, hoje=HOJE, preferencias=self.PREF)
        assert [a["data"] for a in ajustes] == [HOJE]

    def test_dia_passado_sem_treino_continua_intocavel(self):
        """Não adianta reescrever o que já passou: o dia não volta."""
        semana = [dia("2026-08-26", "VO2MAX", 75), dia(HOJE, "TEMPO", 100)]
        assert validar_ajustes(
            [{"data": "2026-08-26", "tipo": "RECUPERACAO", "duracao_min": 60,
              "descricao": "x"}],
            semana, hoje=HOJE, preferencias=self.PREF) == []

    def test_troca_da_sexta_passa(self):
        ajustes = validar_ajustes(
            [{"data": SEXTA, "tipo": "RECUPERACAO", "duracao_min": 60,
              "descricao": "Pedal leve Z1.", "motivo": "quinta virou forte"}],
            self.semana(), hoje=HOJE)
        assert len(ajustes) == 1
        assert ajustes[0]["tipo"] == "RECUPERACAO"
        assert ajustes[0]["motivo"] == "quinta virou forte"

    def test_nao_repoe_volume_perdido(self):
        """Alongar o que sobrou para compensar o longão perdido é justamente o
        que o atleta não quer."""
        ajustes = validar_ajustes(
            [{"data": SEXTA, "tipo": "Z2_LONGO", "duracao_min": 120,
              "descricao": "Repondo o volume da quinta."}],
            self.semana(), hoje=HOJE)
        assert ajustes[0]["duracao_min"] == 75, "a sexta não pode passar do que já tinha"

    def test_mover_sessao_de_dia_e_permitido(self):
        """Trocar o dia de um treino não infla a semana: o total continua igual."""
        ajustes = validar_ajustes(
            [{"data": SEXTA, "tipo": "RECUPERACAO", "duracao_min": 60, "descricao": "leve"},
             {"data": DOMINGO, "tipo": "VO2MAX", "duracao_min": 75, "descricao": "blocos"}],
            self.semana(), hoje=HOJE, preferencias=self.PREF)
        assert {a["data"]: a["tipo"] for a in ajustes} == {
            SEXTA: "RECUPERACAO", DOMINGO: "VO2MAX"}

    def test_dois_dias_duros_colados_viram_duro_mais_leve(self):
        """Quinta foi VO2máx de verdade — sexta não pode ser dura, mesmo que a IA
        insista."""
        ajustes = validar_ajustes(
            [{"data": SEXTA, "tipo": "TIROS", "duracao_min": 70, "descricao": "tiros"}],
            self.semana(), hoje=HOJE)
        assert ajustes[0]["tipo"] == "RECUPERACAO"
        assert ajustes[0]["motivo"]

    def test_semana_de_prova_so_alivia(self):
        ajustes = validar_ajustes(
            [{"data": DOMINGO, "tipo": "VO2MAX", "duracao_min": 75, "descricao": "x"}],
            self.semana(), hoje=HOJE, preferencias=self.PREF,
            estagio_taper="prova", data_prova="2026-09-05")
        assert ajustes == []

    def test_tipo_invalido_e_descartado(self):
        assert validar_ajustes(
            [{"data": SEXTA, "tipo": "PEDALADA_LIVRE", "duracao_min": 60}],
            self.semana(), hoje=HOJE) == []

    def test_dia_sem_treino_do_atleta_vira_descanso(self):
        """Regra de agenda que já existe: dia fora dos dias de treino não recebe
        sessão nenhuma."""
        ajustes = validar_ajustes(
            [{"data": DOMINGO, "tipo": "VO2MAX", "duracao_min": 75, "descricao": "x"}],
            self.semana(), hoje=HOJE,
            preferencias={"dias_treino": [0, 1, 2, 3, 4, 5]})   # sem domingo
        assert ajustes[0]["tipo"] == "DESCANSO"


class TestClasseDeCarga:
    @pytest.mark.parametrize("tipo,classe", [
        ("VO2MAX", "duro"), ("TIROS", "duro"), ("TESTE_FTP", "duro"),
        ("TEMPO", "moderado"), ("FORCA", "moderado"),
        ("Z2_LONGO", "facil"), ("RECUPERACAO", "facil"), ("DESCANSO", "nenhum"),
    ])
    def test_mapa(self, tipo, classe):
        assert classe_do_tipo(tipo) == classe
