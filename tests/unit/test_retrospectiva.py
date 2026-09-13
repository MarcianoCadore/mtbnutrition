"""Retrospectiva do período: como os treinos vêm vindo em 1, 3, 6 ou 12 meses.

A pergunta "como vêm vindo meus treinos?" não se responde com uma semana. O que
o atleta quer ver é o padrão — e o padrão já está escrito: cada treino executado
guarda pontos fortes e fracos na avaliação. Aqui eles são agrupados por tema,
sem nenhuma chamada de IA (as frases já existem; juntar é conta).
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.services import evolucao_service as ev

HOJE = datetime.now(timezone.utc).date()


def dias_atras(n: int) -> str:
    return (HOJE - timedelta(days=n)).isoformat()


def _semana_da(data_iso: str) -> str:
    d = datetime.fromisoformat(data_iso).date()
    return (d - timedelta(days=d.weekday())).isoformat()


def treino(data, tipo="TEMPO", **r):
    base = {"duracao_min": 60, "distancia_km": 30.0, "elevacao_m": 400,
            "tss_obtido": 70, "cadencia_media_rpm": 75}
    base.update(r)
    return {"data": data, "tipo": tipo, "duracao_min": 60, "resultado": base}


async def semear(fake_db, treinos, user="u1"):
    por_semana = {}
    for t in treinos:
        por_semana.setdefault(_semana_da(t["data"]), []).append(t)
    for semana, lista in por_semana.items():
        await fake_db.semanas.insert_one(
            {"user_id": user, "semana_inicio": semana, "treinos": lista})


class TestTemas:
    def test_reconhece_o_assunto_da_frase(self):
        assert ev._tema_de("Cadência média de 69 rpm está abaixo do ideal")[0] == "cadencia"
        assert ev._tema_de("Apenas 2 min em Z5, muito abaixo do esperado")[0] == "zonas"
        assert ev._tema_de("558 m de elevação é elevado para recuperação")[0] == "terreno"

    def test_frase_sem_tema_conhecido_fica_de_fora(self):
        assert ev._tema_de("Sessão concluída conforme combinado") is None

    def test_conta_sessoes_e_nao_frases(self):
        """Uma sessão que repete o mesmo assunto é um problema, não três."""
        agrupado = ev._agrupar([[
            "Cadência média de 69 rpm está baixa",
            "Cadência máxima de 148 rpm foi um pico isolado",
            "Buscar cadência de 85-95 rpm",
        ]])
        assert agrupado[0]["tema"] == "cadencia"
        assert agrupado[0]["n"] == 1

    def test_ordena_do_mais_frequente_para_o_menos(self):
        agrupado = ev._agrupar([
            ["cadência baixa"], ["cadência baixa"], ["cadência baixa"],
            ["pouco tempo em Z5"], ["pouco tempo em Z5"],
            ["558 m de elevação"],
        ])
        assert [x["tema"] for x in agrupado] == ["cadencia", "zonas", "terreno"]
        assert [x["n"] for x in agrupado] == [3, 2, 1]


class TestMesesAtras:
    def test_volta_o_numero_de_meses(self):
        from datetime import date
        assert ev._meses_atras(date(2026, 9, 13), 1) == date(2026, 8, 13)
        assert ev._meses_atras(date(2026, 9, 13), 12) == date(2025, 9, 13)

    def test_encolhe_o_dia_quando_o_mes_e_mais_curto(self):
        from datetime import date
        assert ev._meses_atras(date(2026, 3, 31), 1) == date(2026, 2, 28)


@pytest.mark.asyncio
class TestRetrospectiva:
    async def test_periodo_vazio_nao_quebra(self, fake_db):
        d = await ev.retrospectiva("u1", meses=1)
        assert d["atual"]["sessoes"] == 0
        assert d["fortes"] == [] and d["fracos"] == []

    async def test_soma_o_periodo_pedido(self, fake_db):
        await semear(fake_db, [treino(dias_atras(3)), treino(dias_atras(10)),
                               treino(dias_atras(20))])
        d = await ev.retrospectiva("u1", meses=1)
        assert d["atual"]["sessoes"] == 3
        assert d["atual"]["horas"] == 3.0
        assert d["atual"]["km"] == 90
        assert d["atual"]["cadencia_media"] == 75

    async def test_nao_puxa_treino_de_fora_da_janela(self, fake_db):
        await semear(fake_db, [treino(dias_atras(3)), treino(dias_atras(80))])
        d = await ev.retrospectiva("u1", meses=1)
        assert d["atual"]["sessoes"] == 1

    async def test_compara_com_o_periodo_anterior_de_mesmo_tamanho(self, fake_db):
        """40 horas não diz nada sozinho — o que informa é 40 contra 28."""
        await semear(fake_db, [treino(dias_atras(5)), treino(dias_atras(10))])
        await semear(fake_db, [treino(dias_atras(40))])
        d = await ev.retrospectiva("u1", meses=1)
        assert d["atual"]["sessoes"] == 2
        assert d["anterior"]["sessoes"] == 1

    async def test_agrupa_os_pontos_das_avaliacoes(self, fake_db):
        await semear(fake_db, [
            treino(dias_atras(2), analise_ia={
                "nota": 6.0, "resumo": "ok",
                "pontos_fortes": ["Cumpriu o volume planejado"],
                "pontos_fracos": ["Cadência média baixa (76 rpm)"]}),
            treino(dias_atras(4), analise_ia={
                "nota": 8.0, "resumo": "bom",
                "pontos_fortes": ["Intensidade dentro da zona"],
                "pontos_fracos": ["Cadência média baixa (78 rpm)"]}),
        ])
        d = await ev.retrospectiva("u1", meses=1)
        assert d["fracos"][0]["tema"] == "cadencia"
        assert d["fracos"][0]["n"] == 2
        assert d["atual"]["nota_media"] == 7.0

    async def test_marca_o_melhor_e_o_pior_treino(self, fake_db):
        await semear(fake_db, [
            treino(dias_atras(2), analise_ia={"nota": 9.5, "resumo": "excelente"}),
            treino(dias_atras(5), analise_ia={"nota": 2.0, "resumo": "fora do prescrito"}),
        ])
        d = await ev.retrospectiva("u1", meses=1)
        assert d["melhor"]["nota"] == 9.5
        assert d["pior"]["nota"] == 2.0

    async def test_conta_treino_que_saiu_diferente_do_prescrito(self, fake_db):
        """Recuperação que vira tiro é o padrão mais caro que os dados mostram."""
        await semear(fake_db, [
            treino(dias_atras(2), tipo="RECUPERACAO", tipo_realizado="TIROS"),
            treino(dias_atras(6), tipo="RECUPERACAO", tipo_realizado="TIROS"),
            treino(dias_atras(9), tipo="TEMPO", tipo_realizado="TEMPO"),
        ])
        d = await ev.retrospectiva("u1", meses=1)
        assert d["desvios_total"] == 2
        assert d["desvios"][0]["planejado"] == "RECUPERACAO"
        assert d["desvios"][0]["realizado"] == "TIROS"
        assert d["desvios"][0]["n"] == 2

    async def test_aderencia_sai_de_planejado_contra_executado(self, fake_db):
        await semear(fake_db, [
            treino(dias_atras(2)),
            {"data": dias_atras(4), "tipo": "TEMPO", "duracao_min": 60},   # não feito
        ])
        d = await ev.retrospectiva("u1", meses=1)
        assert d["atual"]["planejados"] == 2
        assert d["atual"]["sessoes"] == 1
        assert d["atual"]["aderencia"] == 50

    async def test_descanso_fica_de_fora_da_conta(self, fake_db):
        await semear(fake_db, [
            treino(dias_atras(2)),
            {"data": dias_atras(3), "tipo": "DESCANSO", "duracao_min": None},
        ])
        d = await ev.retrospectiva("u1", meses=1)
        assert d["atual"]["planejados"] == 1

    async def test_nao_mistura_o_historico_de_outro_atleta(self, fake_db):
        await semear(fake_db, [treino(dias_atras(2))], user="u1")
        await semear(fake_db, [treino(dias_atras(3))], user="u2")
        d = await ev.retrospectiva("u1", meses=1)
        assert d["atual"]["sessoes"] == 1
