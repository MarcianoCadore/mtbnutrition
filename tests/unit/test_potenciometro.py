"""O eixo do alvo é o POTENCIÔMETRO, não indoor/outdoor.

"Indoor" nunca foi a pergunta certa. O atleta que motivou isto tem medidor só
no rolo interativo: a MTB da trilha não mede nada, e o rolo de equilíbrio é
indoor e também não mede. Pela regra antiga ("treino de qualidade é feito no
rolo, logo tem medidor"), um VO2máx no rolo de equilíbrio recebia alvo em watts
que o atleta não tinha como ver.

Quem configura no perfil quantos treinos por semana faz na bike com medidor tem
esses dias marcados pela própria IA ao montar a semana — sem clicar dia a dia.
"""
import pytest

from app.services.config_service import (
    marcar_treinos_com_potencia, tem_potenciometro, treinos_com_potenciometro,
)


def _semana():
    return [
        {"data": "2026-09-07", "tipo": "Z2_LONGO"},
        {"data": "2026-09-08", "tipo": "VO2MAX"},
        {"data": "2026-09-09", "tipo": "ACADEMIA"},
        {"data": "2026-09-10", "tipo": "TIROS"},
        {"data": "2026-09-11", "tipo": "TEMPO"},
        {"data": "2026-09-12", "tipo": "RECUPERACAO"},
        {"data": "2026-09-13", "tipo": "DESCANSO"},
    ]


class TestConfiguracaoDoPerfil:
    def test_le_quantos_treinos_tem_medidor(self):
        assert treinos_com_potenciometro({"potenciometro": {"treinos_semana": 2}}) == 2

    def test_zero_e_uma_resposta_valida(self):
        """Zero significa "não uso medidor em nenhum treino" — diferente de não
        ter configurado."""
        assert treinos_com_potenciometro({"potenciometro": {"treinos_semana": 0}}) == 0

    @pytest.mark.parametrize("user", [
        {}, None, {"potenciometro": {}}, {"potenciometro": {"treinos_semana": None}},
        {"potenciometro": {"treinos_semana": "dois"}},
        {"potenciometro": {"treinos_semana": True}},   # bool não é contagem
    ])
    def test_nao_configurado_volta_none(self, user):
        """None mantém o comportamento antigo para quem já rodava feliz."""
        assert treinos_com_potenciometro(user) is None

    def test_limita_a_semana(self):
        assert treinos_com_potenciometro({"potenciometro": {"treinos_semana": 99}}) == 7
        assert treinos_com_potenciometro({"potenciometro": {"treinos_semana": -3}}) == 0


class TestMarcacaoDaSemana:
    def test_os_mais_duros_ficam_com_o_medidor(self):
        """É no VO2máx que o watt muda a sessão; num Z2 ele quase não importa."""
        treinos = _semana()
        marcar_treinos_com_potencia(treinos, 2)

        com = {t["data"] for t in treinos if t.get("com_potencia")}
        assert com == {"2026-09-08", "2026-09-10"}     # VO2MAX e TIROS

    def test_os_outros_ficam_explicitamente_sem(self):
        """Deixar sem marca faria o envio ao Garmin cair na heurística antiga e
        mandar watts para um dia de MTB."""
        treinos = _semana()
        marcar_treinos_com_potencia(treinos, 1)

        z2 = next(t for t in treinos if t["tipo"] == "Z2_LONGO")
        assert z2["com_potencia"] is False

    def test_academia_e_descanso_ficam_de_fora(self):
        treinos = _semana()
        marcar_treinos_com_potencia(treinos, 7)

        for t in treinos:
            if t["tipo"] in ("ACADEMIA", "DESCANSO"):
                assert "com_potencia" not in t

    def test_zero_deixa_a_semana_toda_em_fc(self):
        treinos = _semana()
        marcar_treinos_com_potencia(treinos, 0)

        assert not any(t.get("com_potencia") for t in treinos)

    def test_pedir_mais_do_que_existe_nao_quebra(self):
        treinos = _semana()
        marcar_treinos_com_potencia(treinos, 99)

        assert sum(1 for t in treinos if t.get("com_potencia")) == 5   # os 5 de bike

    def test_extra_nao_entra_na_conta(self):
        treinos = _semana() + [{"data": "2026-09-08", "tipo": "VO2MAX", "origem": "extra"}]
        marcar_treinos_com_potencia(treinos, 1)

        extra = treinos[-1]
        assert "com_potencia" not in extra


class TestLeituraDoDia:
    def test_campo_novo_manda(self):
        assert tem_potenciometro({"com_potencia": True}) is True
        assert tem_potenciometro({"com_potencia": False}) is False

    def test_treino_antigo_ainda_e_entendido(self):
        """Semanas gravadas antes da troca de eixo guardam `indoor`."""
        assert tem_potenciometro({"indoor": True}) is True
        assert tem_potenciometro({"indoor": False}) is False

    def test_campo_novo_vence_o_antigo(self):
        assert tem_potenciometro({"com_potencia": False, "indoor": True}) is False

    @pytest.mark.parametrize("treino", [{}, None, {"tipo": "TIROS"}])
    def test_sem_marca_volta_none(self, treino):
        """None deixa o envio decidir pelo modo do perfil — não é 'sem medidor'."""
        assert tem_potenciometro(treino) is None
