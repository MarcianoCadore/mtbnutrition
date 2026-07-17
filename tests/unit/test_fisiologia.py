"""Testes do parecer fisiológico (parte determinística do pipeline)."""
import pytest

from app.services.fisiologia_service import (
    calcular_metricas, _parecer_deterministico, bloco_parecer_prompt,
    gerar_parecer_fisiologico,
)


def _treino(data, tipo="Z2_LONGO", executado=True, tss=None, planejado_min=90):
    return {
        "data": data, "tipo": tipo, "planejado_min": planejado_min,
        "executado": executado, "real_min": 90 if executado else None,
        "avg_hr": 150 if executado else None, "max_hr": None,
        "avg_power": None, "norm_power": None,
        "tss_obtido": tss, "tss_esperado": None,
        "resumo_ia": None, "pontos_fracos": [],
    }


def _semana(inicio, treinos):
    return {"semana_inicio": inicio, "treinos": treinos}


class TestCalcularMetricas:
    def test_historico_vazio(self):
        m = calcular_metricas([])
        assert m["carga_aguda"] is None
        assert m["carga_cronica"] is None
        assert m["acwr"] is None
        assert m["aderencia_pct"] is None
        assert m["tss_semanal"] == []

    def test_tss_e_acwr(self):
        # 2 semanas: crônica = (200+300)/2 = 250; aguda = 300 → ACWR 1.2
        m = calcular_metricas([
            _semana("2026-06-29", [_treino("2026-06-29", tss=100), _treino("2026-07-04", tss=100)]),
            _semana("2026-07-06", [_treino("2026-07-06", tss=150), _treino("2026-07-11", tss=150)]),
        ])
        assert m["carga_aguda"] == 300
        assert m["carga_cronica"] == 250
        assert m["acwr"] == 1.2

    def test_acwr_precisa_de_2_semanas_com_tss(self):
        m = calcular_metricas([
            _semana("2026-07-06", [_treino("2026-07-06", tss=200)]),
        ])
        assert m["carga_aguda"] == 200
        assert m["acwr"] is None

    def test_semana_sem_tss_fica_fora_da_cronica(self):
        m = calcular_metricas([
            _semana("2026-06-29", [_treino("2026-06-29", tss=None)]),  # executado sem TSS
            _semana("2026-07-06", [_treino("2026-07-06", tss=200)]),
        ])
        assert m["tss_semanal"][0]["tss"] is None
        assert m["carga_cronica"] == 200

    def test_aderencia_e_furos(self):
        # 4 planejados, 3 executados → 75%. Furo numa quinta (2026-07-09).
        m = calcular_metricas([
            _semana("2026-07-06", [
                _treino("2026-07-06", tss=100),
                _treino("2026-07-07", tss=100),
                _treino("2026-07-09", executado=False),
                _treino("2026-07-11", tss=100),
            ]),
        ])
        assert m["aderencia_pct"] == 75
        assert m["furos_por_dia"] == {"quinta": 1}

    def test_descanso_nao_conta_como_planejado(self):
        m = calcular_metricas([
            _semana("2026-07-06", [
                _treino("2026-07-06", tss=100),
                _treino("2026-07-08", tipo="DESCANSO", executado=False),
            ]),
        ])
        assert m["aderencia_pct"] == 100


class TestParecerDeterministico:
    def test_acwr_alto_reduz(self):
        p = _parecer_deterministico({"acwr": 1.5, "aderencia_pct": 90, "furos_por_dia": {}})
        assert p["ajuste_carga"] == "reduzir"
        assert p["nivel_fadiga"] == "alta"

    def test_acwr_baixo_aumenta(self):
        p = _parecer_deterministico({"acwr": 0.6, "aderencia_pct": 90, "furos_por_dia": {}})
        assert p["ajuste_carga"] == "aumentar"

    def test_faixa_segura_mantem(self):
        p = _parecer_deterministico({"acwr": 1.0, "aderencia_pct": 90, "furos_por_dia": {}})
        assert p["ajuste_carga"] == "manter"

    def test_sem_acwr_mantem(self):
        p = _parecer_deterministico({"acwr": None, "aderencia_pct": None, "furos_por_dia": {}})
        assert p["ajuste_carga"] == "manter"

    def test_aderencia_baixa_vira_ponto_de_atencao(self):
        p = _parecer_deterministico({"acwr": 1.0, "aderencia_pct": 50, "furos_por_dia": {}})
        assert any("Aderência" in x for x in p["pontos_atencao"])

    def test_furos_recorrentes_geram_recomendacao(self):
        p = _parecer_deterministico({"acwr": 1.0, "aderencia_pct": 90,
                                     "furos_por_dia": {"quinta": 3}})
        assert any("quinta" in r for r in p["recomendacoes"])


class TestBlocoParecerPrompt:
    def test_parecer_none_gera_bloco_vazio(self):
        assert bloco_parecer_prompt(None) == ""

    def test_bloco_contem_diretrizes(self):
        bloco = bloco_parecer_prompt({
            "estado_forma": "Atleta absorvendo bem a carga.",
            "nivel_fadiga": "baixa",
            "ajuste_carga": "aumentar",
            "pontos_atencao": ["FC alta nos tiros"],
            "recomendacoes": ["Subir volume do longão"],
            "metricas": {"carga_aguda": 300, "carga_cronica": 250,
                         "acwr": 1.2, "aderencia_pct": 85},
        })
        assert "PARECER FISIOLÓGICO" in bloco
        assert "AUMENTAR" in bloco
        assert "ACWR 1.2" in bloco
        assert "85%" in bloco
        assert "FC alta nos tiros" in bloco
        assert "Subir volume do longão" in bloco


class TestGerarParecer:
    async def test_fallback_deterministico_e_persistencia(self, fake_db, monkeypatch):
        """Sem IA disponível, o parecer determinístico é gerado e salvo no Mongo."""
        import app.services.fisiologia_service as fs

        async def _ia_indisponivel(prompt):
            raise RuntimeError("credit balance is too low")
        monkeypatch.setattr(fs, "_chamar_parecer_ia", _ia_indisponivel)

        await fake_db.semanas.insert_one({
            "user_id": "u1", "semana_inicio": "2026-07-06",
            "treinos": [
                {"data": "2026-07-06", "tipo": "Z2_LONGO", "duracao_min": 120,
                 "resultado": {"duracao_min": 118, "avg_hr": 145, "tss_obtido": 120}},
                {"data": "2026-07-08", "tipo": "VO2MAX", "duracao_min": 75,
                 "resultado": None},
            ],
        })

        parecer = await gerar_parecer_fisiologico("u1", "2026-07-06")

        assert parecer["modelo"] == "deterministico"
        assert parecer["ajuste_carga"] in ("aumentar", "manter", "reduzir")
        assert parecer["metricas"]["aderencia_pct"] == 50

        salvo = await fake_db.pareceres_fisiologicos.find_one(
            {"user_id": "u1", "semana_ref": "2026-07-06"})
        assert salvo is not None
        assert salvo["modelo"] == "deterministico"

    async def test_usa_parecer_da_ia_quando_disponivel(self, fake_db, monkeypatch):
        import app.services.fisiologia_service as fs

        async def _ia_ok(prompt):
            return ({"estado_forma": "Boa absorção de carga.",
                     "nivel_fadiga": "baixa", "ajuste_carga": "aumentar",
                     "pontos_atencao": [], "recomendacoes": ["Progredir o longão"]},
                    "claude-opus")
        monkeypatch.setattr(fs, "_chamar_parecer_ia", _ia_ok)

        await fake_db.semanas.insert_one({
            "user_id": "u1", "semana_inicio": "2026-07-06", "treinos": []})

        parecer = await gerar_parecer_fisiologico("u1", "2026-07-06")
        assert parecer["modelo"] == "claude-opus"
        assert parecer["ajuste_carga"] == "aumentar"
        assert parecer["recomendacoes"] == ["Progredir o longão"]


class TestPipelineIntegrado:
    async def test_gerar_proxima_semana_inclui_parecer(self, fake_db, monkeypatch):
        """Pipeline completo sem IA: parecer determinístico entra no prompt e no retorno."""
        import app.services.fisiologia_service as fs
        import app.services.plano_semana_service as ps

        # IA indisponível nos dois passos; sem Gemini → fallback determinístico
        prompts_enviados = []

        class _ClientQuotaEsgotada:
            class messages:
                @staticmethod
                async def create(**kwargs):
                    prompts_enviados.append(kwargs["messages"][0]["content"])
                    raise RuntimeError("credit balance is too low")

        monkeypatch.setattr(ps, "_client", _ClientQuotaEsgotada)

        async def _ia_indisponivel(prompt):
            raise RuntimeError("credit balance is too low")
        monkeypatch.setattr(fs, "_chamar_parecer_ia", _ia_indisponivel)
        monkeypatch.setattr(ps.settings, "GEMINI_API_KEY", "")

        await fake_db.semanas.insert_one({
            "user_id": "u1", "semana_inicio": "2026-07-06",
            "treinos": [
                {"data": "2026-07-06", "tipo": "Z2_LONGO", "duracao_min": 120,
                 "resultado": {"duracao_min": 118, "avg_hr": 145, "tss_obtido": 120}},
                {"data": "2026-07-08", "tipo": "VO2MAX", "duracao_min": 75,
                 "resultado": {"duracao_min": 74, "avg_hr": 168, "tss_obtido": 90}},
            ],
        })

        plano = await ps.gerar_proxima_semana("u1", "2026-07-06")

        # parecer presente no retorno (mesmo com toda a IA fora do ar)
        assert plano["parecer_fisiologico"] is not None
        assert plano["parecer_fisiologico"]["modelo"] == "deterministico"
        # o prompt da geração recebeu o bloco do parecer
        assert prompts_enviados, "geração deveria ter tentado chamar o modelo"
        assert "PARECER FISIOLÓGICO" in prompts_enviados[0]
        # geração caiu no fallback determinístico e ainda entregou a semana
        # (o fallback espelha os treinos da semana atual — 2 dias semeados)
        assert plano["modelo_usado"] == "fallback"
        assert len(plano["treinos"]) == 2
        assert all(t["data"].startswith("2026-07-1") for t in plano["treinos"])
