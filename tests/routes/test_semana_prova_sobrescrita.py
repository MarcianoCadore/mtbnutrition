"""A semana de polimento não pode ser desfeita por um salvamento da grade.

Em 12/09/2026, seis dias antes de uma prova prioridade A, a semana de polimento
(3h30, sábado livre para a prova) virou 9h55 com 4h30 de pedal no dia da prova.
A escrita veio do portal — a grade mandou o plano que tinha em memória, que era
a semana mecânica de +5% anterior.

Dois buracos apareceram na investigação, e são estes que os testes abaixo
prendem: o documento gravado fora do portal não carimbava versão (então a aba
velha nem levava 409), e o salvamento trocava o documento inteiro pelo payload,
apagando os campos que o modelo não conhece.
"""
from datetime import date, timedelta

import pytest

_HOJE = date.today()
SEG = (_HOJE + timedelta(days=(7 - _HOJE.weekday()))).isoformat()


def dia(n):
    return (date.fromisoformat(SEG) + timedelta(days=n)).isoformat()


def _semana_polimento():
    """Como o script do Claude Code grava a semana de prova."""
    return {
        "semana_inicio": SEG, "objetivo": "polimento", "gerada_por_ia": True,
        "atualizado_em": "2026-01-01T00:00:00+00:00",
        "treinos": [
            {"data": dia(0), "tipo": "RECUPERACAO", "duracao_min": 60, "descricao": "Z1 plano"},
            {"data": dia(1), "tipo": "VO2MAX", "duracao_min": 60, "descricao": "4x2min Z5"},
            {"data": dia(2), "tipo": "RECUPERACAO", "duracao_min": 50, "descricao": "Z1 plano"},
            {"data": dia(3), "tipo": "DESCANSO", "duracao_min": None, "descricao": "Descanso total"},
            {"data": dia(4), "tipo": "RECUPERACAO", "duracao_min": 40, "descricao": "ativacao"},
            {"data": dia(5), "tipo": "DESCANSO", "duracao_min": None, "descricao": "DIA DA PROVA"},
            {"data": dia(6), "tipo": "DESCANSO", "duracao_min": None, "descricao": ""},
        ],
    }


def _grade_antiga():
    """O que uma aba com a semana mecânica de +5% manda ao salvar."""
    return [
        {"data": dia(0), "tipo": "RECUPERACAO", "duracao_min": 60, "descricao": "Z1 plano"},
        {"data": dia(1), "tipo": "VO2MAX", "duracao_min": 60, "descricao": "4x2min Z5"},
        {"data": dia(2), "tipo": "RECUPERACAO", "duracao_min": 50, "descricao": "Z1 plano"},
        {"data": dia(3), "tipo": "TEMPO", "duracao_min": 115, "descricao": "tempo +5%"},
        {"data": dia(4), "tipo": "RECUPERACAO", "duracao_min": 40, "descricao": "ativacao"},
        {"data": dia(5), "tipo": "Z2_LONGO", "duracao_min": 270, "descricao": "longao"},
        {"data": dia(6), "tipo": "DESCANSO"},
    ]


class TestDiaDaProva:
    def test_descanso_futuro_nao_vira_treino(self, auth_client, fake_db, run):
        """Dia livre numa semana futura é decisão de plano, não campo vazio."""
        client, uid = auth_client
        run(fake_db.semanas.insert_one({**_semana_polimento(), "user_id": uid}))

        client.post("/workout/semana", json={
            "semana_inicio": SEG, "objetivo": "", "treinos": _grade_antiga()})

        doc = run(fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": uid}))
        por_data = {t["data"]: t for t in doc["treinos"]}
        assert str(por_data[dia(5)]["tipo"]) == "DESCANSO", "o dia da prova recebeu treino"
        assert str(por_data[dia(3)]["tipo"]) == "DESCANSO", "o descanso do polimento virou treino"

    def test_aba_aberta_antes_da_gravacao_leva_409(self, auth_client, fake_db, run):
        """Quem leu a semana antes dela mudar não pode salvar por cima calado."""
        client, uid = auth_client
        run(fake_db.semanas.insert_one({**_semana_polimento(), "user_id": uid}))

        r = client.post("/workout/semana", json={
            "semana_inicio": SEG, "objetivo": "", "treinos": _grade_antiga(),
            "base_versao": "2025-12-25T00:00:00+00:00"})   # versão de antes
        assert r.status_code == 409

    def test_versao_vazia_nao_casa_com_semana_carimbada(self, auth_client, fake_db, run):
        """Aba que leu a semana quando ela ainda não tinha carimbo também é velha."""
        client, uid = auth_client
        run(fake_db.semanas.insert_one({**_semana_polimento(), "user_id": uid}))

        r = client.post("/workout/semana", json={
            "semana_inicio": SEG, "objetivo": "", "treinos": _grade_antiga(),
            "base_versao": ""})
        assert r.status_code == 409


class TestCamposForaDoModelo:
    def test_marca_de_semana_gerada_pela_ia_sobrevive(self, auth_client, fake_db, run):
        """`gerada_por_ia` não está em TreinoSemana — e some se o replace_one não olhar."""
        client, uid = auth_client
        run(fake_db.semanas.insert_one({**_semana_polimento(), "user_id": uid}))

        client.post("/workout/semana", json={
            "semana_inicio": SEG, "objetivo": "", "treinos": _grade_antiga()})

        doc = run(fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": uid}))
        assert doc.get("gerada_por_ia") is True
