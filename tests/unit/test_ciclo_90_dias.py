"""O ciclo de 90 dias é o que dá memória longa ao treinador.

O defeito que motivou tudo isto está no parecer de 13/09/2026: ACWR 1.69 com
"nenhuma semana de descarga feita no bloco". Não havia bloco — cada semana era
a primeira. Estes testes prendem as duas metades da correção:

1. o ESQUELETO garante que a descarga existe por construção, em qualquer
   configuração de calendário (com prova, sem prova, prova no meio do ciclo);
2. a TRAVA garante que uma semana marcada como descarga não sai do funil de
   `normalizar_plano` com três sessões duras dentro.
"""
import pytest

from app.services import ciclo_service as cs
from app.services.plano_semana_service import normalizar_plano

INICIO = "2026-09-21"   # segunda-feira


# ── Esqueleto ────────────────────────────────────────────────────────────────

def _semanas_planas(blocos):
    return [d for b in blocos for d in b["semanas_detalhe"]]


def test_ciclo_cobre_13_semanas_exatas_sem_buraco_nem_sobreposicao():
    blocos = cs.esqueleto_blocos(INICIO, provas=[], carga_cronica=440)
    semanas = [d["semana"] for d in _semanas_planas(blocos)]

    assert len(semanas) == cs.SEMANAS_CICLO
    assert semanas == sorted(semanas), "semanas fora de ordem"
    assert len(set(semanas)) == len(semanas), "semana repetida entre blocos"
    assert semanas[0] == INICIO
    assert cs.fim_do_ciclo(INICIO) == "2026-12-20"


def test_todo_bloco_de_carga_termina_em_descarga():
    """O ACWR 1.69 aconteceu porque nenhum bloco tinha fim. Agora tem."""
    blocos = cs.esqueleto_blocos(INICIO, provas=[], carga_cronica=440)

    for bloco in blocos:
        if bloco["foco"] in ("taper", "transicao") or bloco["semanas"] <= 2:
            continue
        papeis = [d["papel"] for d in bloco["semanas_detalhe"]]
        assert papeis[-1] == cs.PAPEL_DESCARGA, (
            f"bloco {bloco['n']} ({bloco['foco']}) termina em {papeis[-1]}, "
            "não em descarga"
        )
        assert papeis.count(cs.PAPEL_DESCARGA) == 1


def test_sem_prova_o_ciclo_e_de_desenvolvimento_e_fecha_medindo():
    blocos = cs.esqueleto_blocos(INICIO, provas=[], carga_cronica=440)
    papeis = [d["papel"] for d in _semanas_planas(blocos)]

    assert [b["foco"] for b in blocos][:3] == ["base", "construcao", "construcao"]
    # Sem data de largada não se inventa pico.
    assert "pico" not in [b["foco"] for b in blocos]
    # O ciclo fecha aferindo: abrir com diagnóstico e fechar sem medida seria
    # prometer evolução sem comprovar.
    assert papeis[-1] == cs.PAPEL_TESTE


def test_com_prova_o_ciclo_alinha_de_tras_para_frente():
    """A data da largada é a única que não se negocia."""
    prova = {"nome": "XCO", "data": "2026-11-29", "prioridade": "A"}
    blocos = cs.esqueleto_blocos(INICIO, provas=[prova], carga_cronica=440)
    det = {d["semana"]: d["papel"] for d in _semanas_planas(blocos)}

    assert det[cs.segunda_de("2026-11-29")] == cs.PAPEL_PROVA
    assert det["2026-11-16"] == cs.PAPEL_TAPER        # descarga do polimento
    assert [b["foco"] for b in blocos if b["foco"] == "pico"], "faltou bloco de pico"
    # Nada de qualidade sobrando depois: a semana seguinte à prova é transição.
    assert det["2026-11-30"] == cs.PAPEL_TRANSICAO


def test_prova_de_prioridade_A_ganha_da_prova_mais_proxima():
    """Provas distantes não são uma temporada: entre elas se constrói."""
    provas = [
        {"nome": "treino longo", "data": "2026-10-11", "prioridade": "C"},
        {"nome": "o alvo", "data": "2026-11-29", "prioridade": "A"},
    ]
    blocos = cs.esqueleto_blocos(INICIO, provas=provas, carga_cronica=440)
    det = {d["semana"]: d["papel"] for d in _semanas_planas(blocos)}

    # 7 semanas de intervalo: o ciclo se organiza em torno da prova A...
    assert det[cs.segunda_de("2026-11-29")] == cs.PAPEL_PROVA
    assert det["2026-11-16"] == cs.PAPEL_TAPER
    assert "competicao" not in [b["foco"] for b in blocos]
    # ...e a etapa C solta não vira semana de carga cheia, mas também não
    # reorganiza o ciclo em volta dela.
    assert det[cs.segunda_de("2026-10-11")] == cs.PAPEL_PROVA


def test_carga_progride_dentro_do_bloco_e_cai_na_descarga():
    blocos = cs.esqueleto_blocos(INICIO, provas=[], carga_cronica=400)
    primeiro = blocos[0]["semanas_detalhe"]
    alvos = [d["alvo_tss"] for d in primeiro]

    assert alvos[0] < alvos[1] < alvos[2], "as semanas de carga não progridem"
    assert alvos[-1] < alvos[0], "a descarga não é mais leve que a 1ª semana"
    # Nenhum salto isolado como o 387 → 745 que estourou o ACWR.
    for antes, depois in zip(alvos, alvos[1:]):
        assert depois <= antes * 1.3


def test_carga_sobe_de_um_bloco_para_o_proximo():
    blocos = cs.esqueleto_blocos(INICIO, provas=[], carga_cronica=400)
    pico_por_bloco = [
        max(d["alvo_tss"] for d in b["semanas_detalhe"])
        for b in blocos if b["semanas"] > 1
    ]
    assert pico_por_bloco == sorted(pico_por_bloco)
    assert pico_por_bloco[-1] > pico_por_bloco[0], "90 dias sem progressão nenhuma"


def test_sem_carga_cronica_o_ciclo_existe_mas_nao_inventa_numero():
    """Atleta novo tem estrutura; não tem alvo de TSS chutado."""
    blocos = cs.esqueleto_blocos(INICIO, provas=[], carga_cronica=None)

    assert len(_semanas_planas(blocos)) == cs.SEMANAS_CICLO
    assert all(d["alvo_tss"] is None for d in _semanas_planas(blocos))


# ── Posição ──────────────────────────────────────────────────────────────────

def _ciclo(**extra):
    c = {
        "numero": 1,
        "inicio": INICIO,
        "fim": cs.fim_do_ciclo(INICIO),
        "objetivo": "subir o FTP",
        "blocos": cs.esqueleto_blocos(INICIO, provas=[], carga_cronica=440),
    }
    c.update(extra)
    return c


def test_posicao_localiza_a_semana_no_bloco():
    pos = cs.posicao(_ciclo(), "2026-10-05")   # 3ª semana do ciclo

    assert pos["semana_no_ciclo"] == 3
    assert pos["n_bloco"] == 1
    assert pos["semana_no_bloco"] == 3
    assert pos["semanas_restantes"] == cs.SEMANAS_CICLO - 3


def test_posicao_marca_a_semana_de_descarga():
    pos = cs.posicao(_ciclo(), "2026-10-12")   # 4ª semana = descarga
    assert pos["eh_descarga"] is True
    assert pos["papel"] == cs.PAPEL_DESCARGA


def test_posicao_aceita_qualquer_dia_da_semana():
    """Quem chama passa a segunda, mas um domingo não pode devolver None."""
    assert cs.posicao(_ciclo(), "2026-10-11")["semana_no_ciclo"] == 3


def test_sem_ciclo_ou_fora_da_janela_nao_quebra():
    assert cs.posicao(None, "2026-10-05") is None
    assert cs.posicao(_ciclo(), "2027-03-01") is None
    assert cs.bloco_prompt(None, "2026-10-05") == ""


# ── Bloco de prompt ──────────────────────────────────────────────────────────

def test_prompt_diz_onde_o_atleta_esta_e_o_que_persegue():
    ciclo = _ciclo(
        limitadores=[{
            "nome": "Dia fácil não é fácil",
            "evidencia": "RECUPERACAO entregou 2-3x o TSS previsto",
            "como_atacar": "teto de watts explícito nos dias fáceis",
            "bloco_alvo": 1,
        }],
        metas=[{"chave": "ftp", "descricao": "FTP", "de": 300, "para": 320, "unidade": "W"}],
    )
    txt = cs.bloco_prompt(ciclo, "2026-09-28")

    assert "BLOCO 1" in txt
    assert "semana 2 de 13" in txt.lower()
    assert "Dia fácil não é fácil" in txt
    assert "300 → 320 W" in txt
    assert "subir o FTP" in txt


def test_prompt_da_semana_de_descarga_avisa_em_alto_e_bom_som():
    txt = cs.bloco_prompt(_ciclo(), "2026-10-12")
    assert "DESCARGA" in txt
    assert "absorver" in txt


def test_prompt_mostra_o_alvo_de_tss_da_semana():
    txt = cs.bloco_prompt(_ciclo(), "2026-09-21")
    assert "ALVO DE CARGA DESTA SEMANA" in txt


def test_limitador_de_outro_bloco_nao_polui_a_semana():
    ciclo = _ciclo(limitadores=[
        {"nome": "cadência baixa", "como_atacar": "x", "bloco_alvo": 3},
    ])
    assert "cadência baixa" not in cs.bloco_prompt(ciclo, "2026-09-21")
    assert "cadência baixa" in cs.bloco_prompt(ciclo, "2026-11-23")


# ── Trava da descarga em normalizar_plano ────────────────────────────────────

def _ctx(pos_ciclo=None):
    return {
        "proxima": "2026-09-21",
        "preferencias": {"dias_treino": [0, 1, 2, 3, 4, 5]},
        "fase_prova": None,
        "estagio_prova": None,
        "data_prova": None,
        "zonas_lista": [],
        "zonas_pot_user": [],
        "quantos_com_potencia": None,
        "parecer": None,
        "ciclo": {"numero": 1},
        "pos_ciclo": pos_ciclo,
    }


def _semana_dura():
    return {"analise_semana": "", "progressao": "", "treinos": [
        {"data": "2026-09-21", "tipo": "VO2MAX", "duracao_min": 75, "descricao": "5x4min Z5"},
        {"data": "2026-09-22", "tipo": "RECUPERACAO", "duracao_min": 45, "descricao": "leve"},
        {"data": "2026-09-23", "tipo": "TIROS", "duracao_min": 80, "descricao": "8x2min"},
        {"data": "2026-09-24", "tipo": "RECUPERACAO", "duracao_min": 45, "descricao": "leve"},
        {"data": "2026-09-25", "tipo": "TEMPO", "duracao_min": 90, "descricao": "3x15min Z3"},
        {"data": "2026-09-26", "tipo": "Z2_LONGO", "duracao_min": 180, "descricao": "longão"},
    ]}


def test_descarga_derruba_as_sessoes_duras_alem_da_primeira():
    pos = {"eh_descarga": True, "n_bloco": 1, "papel": cs.PAPEL_DESCARGA,
           "semana_no_bloco": 4, "semana_no_ciclo": 4, "alvo_tss": 264,
           "bloco": {"foco": "base"}}
    out = normalizar_plano(_semana_dura(), _ctx(pos))

    duras = [t for t in out["treinos"] if t["tipo"] in ("VO2MAX", "TIROS", "TEMPO", "FORCA")]
    assert len(duras) == 1, "descarga com mais de uma sessão de qualidade"
    assert duras[0]["tipo"] == "VO2MAX", "a abertura preservada deve ser a primeira"


def test_descarga_corta_o_longao_mas_nao_zera_a_intensidade():
    pos = {"eh_descarga": True, "n_bloco": 1, "papel": cs.PAPEL_DESCARGA,
           "semana_no_bloco": 4, "semana_no_ciclo": 4, "alvo_tss": 264,
           "bloco": {"foco": "base"}}
    out = normalizar_plano(_semana_dura(), _ctx(pos))
    por_dia = {t["data"]: t for t in out["treinos"]}

    assert por_dia["2026-09-26"]["duracao_min"] == 120
    # Zerar a intensidade destreinaria justo na semana da adaptação.
    assert por_dia["2026-09-21"]["tipo"] == "VO2MAX"
    assert por_dia["2026-09-21"]["duracao_min"] == 75


def test_semana_de_carga_passa_intacta():
    pos = {"eh_descarga": False, "n_bloco": 1, "papel": cs.PAPEL_CARGA,
           "semana_no_bloco": 2, "semana_no_ciclo": 2, "alvo_tss": 475,
           "bloco": {"foco": "base"}}
    out = normalizar_plano(_semana_dura(), _ctx(pos))

    duras = [t for t in out["treinos"] if t["tipo"] in ("VO2MAX", "TIROS", "TEMPO")]
    assert len(duras) == 3


def test_sem_ciclo_o_plano_sai_como_sempre_saiu():
    """Atleta sem ciclo não pode ter a semana alterada por causa disto."""
    out = normalizar_plano(_semana_dura(), _ctx(pos_ciclo=None))

    assert out["ciclo"] is None
    duras = [t for t in out["treinos"] if t["tipo"] in ("VO2MAX", "TIROS", "TEMPO")]
    assert len(duras) == 3


def test_plano_guarda_onde_a_semana_caiu_no_ciclo():
    pos = {"eh_descarga": False, "n_bloco": 2, "papel": cs.PAPEL_CARGA,
           "semana_no_bloco": 1, "semana_no_ciclo": 5, "alvo_tss": 462,
           "bloco": {"foco": "construcao"}}
    out = normalizar_plano(_semana_dura(), _ctx(pos))

    assert out["ciclo"] == {
        "numero": 1, "n_bloco": 2, "foco": "construcao",
        "semana_no_bloco": 1, "semana_no_ciclo": 5,
        "papel": cs.PAPEL_CARGA, "alvo_tss": 462,
    }


def test_semana_da_prova_e_muito_mais_leve_que_uma_descarga_comum():
    """Taper e ciclo não podem discordar sobre quanto cortar."""
    from app.services.prova_service import _FRACAO_CARGA_TAPER

    prova = {"nome": "XCO", "data": "2026-11-29", "prioridade": "A"}
    blocos = cs.esqueleto_blocos(INICIO, provas=[prova], carga_cronica=442)
    det = {d["semana"]: d for d in _semanas_planas(blocos)}

    alvo_taper = det["2026-11-16"]["alvo_tss"]
    alvo_prova = det["2026-11-23"]["alvo_tss"]
    assert alvo_prova < alvo_taper
    assert alvo_prova / alvo_taper == pytest.approx(
        _FRACAO_CARGA_TAPER["prova"] / _FRACAO_CARGA_TAPER["descarga"], abs=0.02)


# ── Carga de referência ──────────────────────────────────────────────────────

# As 12 semanas reais do Marciano em 20/09/2026, com o pico pré-prova (745), as
# semanas sem dado de TSS (0) e a subestimação sistemática (900 min → 387 TSS).
SEMANAL_REAL = [
    {"semana": "2026-06-29", "tss": 523}, {"semana": "2026-07-06", "tss": 384},
    {"semana": "2026-07-13", "tss": 478}, {"semana": "2026-07-20", "tss": 662},
    {"semana": "2026-07-27", "tss": 488}, {"semana": "2026-08-03", "tss": 171},
    {"semana": "2026-08-10", "tss": 0},   {"semana": "2026-08-17", "tss": 95},
    {"semana": "2026-08-24", "tss": 540}, {"semana": "2026-08-31", "tss": 387},
    {"semana": "2026-09-07", "tss": 745}, {"semana": "2026-09-14", "tss": 0},
]


def test_carga_de_referencia_ignora_semanas_sem_dado():
    """TSS zerado quase sempre é falta de DADO, não de treino."""
    com_zeros = cs.carga_de_referencia(SEMANAL_REAL)
    sem_zeros = cs.carga_de_referencia([s for s in SEMANAL_REAL if s["tss"]])
    assert com_zeros == sem_zeros


def test_carga_de_referencia_nao_e_puxada_pelo_pico_pre_prova():
    """O erro real: a janela de 4 semanas pegou o pico e mandou abrir acima dele."""
    ref = cs.carga_de_referencia(SEMANAL_REAL)
    pico = max(s["tss"] for s in SEMANAL_REAL)

    assert ref < pico
    # E o bloco de BASE não pode abrir acima do que o atleta já sustentou.
    blocos = cs.esqueleto_blocos("2026-09-21", provas=[], carga_cronica=ref)
    assert max(d["alvo_tss"] for d in _semanas_planas(blocos)) <= pico


def test_carga_de_referencia_sem_historico_nenhum():
    assert cs.carga_de_referencia([]) is None
    assert cs.carga_de_referencia([{"semana": "x", "tss": 0}]) is None


# ── Resíduo de prova recém-corrida ───────────────────────────────────────────

CARCARA = {"nome": "Campeonato XCO Carcará", "data": "2026-09-19", "prioridade": "A"}


def test_ciclo_que_abre_logo_depois_de_uma_prova_comeca_absorvendo():
    """Carregar na semana seguinte à largada é o erro que nenhum treinador comete."""
    blocos = cs.esqueleto_blocos(INICIO, provas=[CARCARA], carga_cronica=480)
    primeira = _semanas_planas(blocos)[0]

    assert primeira["semana"] == INICIO
    assert primeira["papel"] == cs.PAPEL_TRANSICAO
    assert blocos[0]["foco"] == "transicao"


def test_transicao_de_abertura_nao_come_a_semana_de_afericao():
    """A transição sai do orçamento de semanas; o ciclo continua fechando medindo."""
    blocos = cs.esqueleto_blocos(INICIO, provas=[CARCARA], carga_cronica=480)
    papeis = [d["papel"] for d in _semanas_planas(blocos)]

    assert len(papeis) == cs.SEMANAS_CICLO
    assert papeis[-1] == cs.PAPEL_TESTE
    # E cada bloco de carga continua tendo o seu fim.
    for b in blocos:
        if b["foco"] in ("taper", "transicao", "afericao") or b["semanas"] <= 2:
            continue
        assert [d["papel"] for d in b["semanas_detalhe"]][-1] == cs.PAPEL_DESCARGA


def test_prova_C_recente_nao_justifica_abrir_em_transicao():
    """Pedalada de prioridade C não deixa resíduo que valha uma semana do ciclo."""
    pedalada = {"nome": "giro", "data": "2026-09-19", "prioridade": "C"}
    blocos = cs.esqueleto_blocos(INICIO, provas=[pedalada], carga_cronica=480)
    assert _semanas_planas(blocos)[0]["papel"] == cs.PAPEL_CARGA


def test_prova_antiga_nao_conta_como_residuo():
    velha = {"nome": "antiga", "data": "2026-08-01", "prioridade": "A"}
    blocos = cs.esqueleto_blocos(INICIO, provas=[velha], carga_cronica=480)
    assert _semanas_planas(blocos)[0]["papel"] == cs.PAPEL_CARGA


# ── Meta de volume × semana de descarga ──────────────────────────────────────

def test_papel_do_ciclo_que_nao_e_carga_suspende_a_meta_de_volume():
    """Meta de 10h contra semana de prova de 6h: duas ordens contraditórias.

    A meta é um número e o papel é prosa — sem a exceção explícita o gerador
    obedece à meta e a semana de prova volta a ser semana cheia.
    """
    from app.services.plano_semana_service import _excecao_meta_volume

    for papel in (cs.PAPEL_DESCARGA, cs.PAPEL_PROVA, cs.PAPEL_TAPER,
                  cs.PAPEL_TRANSICAO, cs.PAPEL_TESTE):
        txt = _excecao_meta_volume({"papel": papel, "eh_descarga": False}, None)
        assert "A META NÃO VALE" in txt, f"{papel} não suspendeu a meta"
        assert papel.upper() in txt


def test_meta_de_volume_vale_na_carga_e_na_manutencao():
    """Nesses dois papéis o alvo de horas e o de TSS dizem a mesma coisa."""
    from app.services.plano_semana_service import _excecao_meta_volume

    for papel in (cs.PAPEL_CARGA, cs.PAPEL_MANUTENCAO):
        txt = _excecao_meta_volume({"papel": papel, "eh_descarga": False}, None)
        assert "A META NÃO VALE" not in txt, f"{papel} suspendeu a meta sem motivo"


def test_o_papel_do_ciclo_manda_mais_que_o_polimento_de_prova():
    """Se as duas valerem, a mensagem tem que ser uma só — e a do ciclo."""
    from app.services.plano_semana_service import _excecao_meta_volume

    txt = _excecao_meta_volume({"papel": cs.PAPEL_DESCARGA, "eh_descarga": True}, "descarga")
    assert "DESCARGA" in txt
    assert txt.count("A META NÃO VALE") == 1


def test_sem_ciclo_o_comportamento_antigo_da_prova_continua():
    from app.services.plano_semana_service import _excecao_meta_volume

    assert "polimento/prova" in _excecao_meta_volume(None, "prova")
    assert "ÚNICA exceção" in _excecao_meta_volume(None, None)


# ── Bloco de competição ──────────────────────────────────────────────────────

# O calendário real do Marciano: quatro provas em seis semanas e depois sete
# semanas limpas. Não existe taper que sirva para as quatro.
TEMPORADA = [
    {"nome": "etapa", "data": "2026-09-27", "prioridade": "B"},
    {"nome": "XCO", "data": "2026-10-03", "prioridade": "B"},
    {"nome": "XCO", "data": "2026-10-24", "prioridade": "B"},
    {"nome": "XCM Passo Fundo", "data": "2026-11-01", "prioridade": "B"},
]


def test_provas_agrupadas_viram_bloco_de_competicao():
    blocos = cs.esqueleto_blocos(INICIO, provas=TEMPORADA, carga_cronica=483)
    focos = [b["foco"] for b in blocos]

    assert "competicao" in focos
    # Não se poliria quatro vezes: nenhum taper isolado no meio da temporada.
    comp = next(b for b in blocos if b["foco"] == "competicao")
    assert cs.PAPEL_TAPER not in [d["papel"] for d in comp["semanas_detalhe"]]


def test_toda_semana_com_prova_e_marcada_como_tal():
    blocos = cs.esqueleto_blocos(INICIO, provas=TEMPORADA, carga_cronica=483)
    det = {d["semana"]: d["papel"] for d in _semanas_planas(blocos)}

    for p in TEMPORADA:
        assert det[cs.segunda_de(p["data"])] == cs.PAPEL_PROVA, f"{p['data']} não marcada"


def test_semana_entre_duas_provas_e_manutencao_nao_construcao():
    """Duas semanas entre largadas não mudam fisiologia — fingir que mudam é o erro."""
    blocos = cs.esqueleto_blocos(INICIO, provas=TEMPORADA, carga_cronica=483)
    det = {d["semana"]: d["papel"] for d in _semanas_planas(blocos)}

    assert det["2026-10-05"] == cs.PAPEL_MANUTENCAO
    assert det["2026-10-12"] == cs.PAPEL_MANUTENCAO


def test_o_desenvolvimento_de_verdade_vem_depois_da_ultima_prova():
    blocos = cs.esqueleto_blocos(INICIO, provas=TEMPORADA, carga_cronica=483)
    det = {d["semana"]: d for d in _semanas_planas(blocos)}

    # Semana seguinte ao XCM: transição, não carga.
    assert det["2026-11-02"]["papel"] == cs.PAPEL_TRANSICAO
    # E as sete semanas finais carregam de verdade, terminando em descarga+teste.
    depois = [d["papel"] for s, d in sorted(det.items()) if s >= "2026-11-09"]
    assert cs.PAPEL_CARGA in depois
    assert depois[-1] == cs.PAPEL_TESTE
    assert cs.PAPEL_DESCARGA in depois, "bloco de desenvolvimento sem descarga"


def test_competicao_nao_conta_como_degrau_de_progressao():
    """Sustentar forma não é construir: o alvo-base não sobe durante a temporada."""
    blocos = cs.esqueleto_blocos(INICIO, provas=TEMPORADA, carga_cronica=483)
    comp = next(b for b in blocos if b["foco"] == "competicao")
    dev = [b for b in blocos if b["foco"] in cs._SEQUENCIA_SEM_PROVA]

    pico_comp = max(d["alvo_tss"] for d in comp["semanas_detalhe"])
    pico_dev = max(d["alvo_tss"] for b in dev for d in b["semanas_detalhe"])
    assert pico_comp < pico_dev


def test_semana_de_prova_do_bloco_nao_e_tao_leve_quanto_um_taper():
    blocos = cs.esqueleto_blocos(INICIO, provas=TEMPORADA, carga_cronica=483)
    det = {d["semana"]: d for d in _semanas_planas(blocos)}
    assert det["2026-09-21"]["alvo_tss"] == round(483 * cs.FRACAO_SEMANA_PROVA)


def test_prova_A_entre_varias_ganha_polimento_se_houver_semana_livre():
    """Se uma delas importar mais, a semana anterior vira taper — as outras não."""
    temporada = [
        {"nome": "etapa", "data": "2026-09-27", "prioridade": "B"},
        {"nome": "XCO", "data": "2026-10-03", "prioridade": "B"},
        {"nome": "XCM Passo Fundo", "data": "2026-10-25", "prioridade": "A"},
    ]
    blocos = cs.esqueleto_blocos(INICIO, provas=temporada, carga_cronica=483)
    det = {d["semana"]: d["papel"] for d in _semanas_planas(blocos)}

    assert det["2026-10-19"] == cs.PAPEL_PROVA      # semana do XCM (domingo 25/10)
    assert det["2026-10-12"] == cs.PAPEL_TAPER      # véspera: polimento só para a A
    assert det["2026-10-05"] == cs.PAPEL_MANUTENCAO


def test_nao_se_inventa_taper_numa_semana_que_ja_tem_prova():
    """Com prova no sábado anterior, a véspera do alvo não pode virar polimento."""
    temporada = [dict(p) for p in TEMPORADA]
    temporada[-1]["prioridade"] = "A"          # XCM em 01/11, XCO em 24/10
    blocos = cs.esqueleto_blocos(INICIO, provas=temporada, carga_cronica=483)
    det = {d["semana"]: d["papel"] for d in _semanas_planas(blocos)}

    assert det["2026-10-19"] == cs.PAPEL_PROVA   # é semana de prova, não de taper
    assert det["2026-10-26"] == cs.PAPEL_PROVA


def test_prova_na_primeira_semana_dispensa_a_transicao_de_abertura():
    """A semana já vai ser leve pela prova — gastar outra com transição é perder duas."""
    provas = TEMPORADA + [CARCARA]
    blocos = cs.esqueleto_blocos(INICIO, provas=provas, carga_cronica=483)
    primeira = _semanas_planas(blocos)[0]

    assert primeira["semana"] == INICIO
    assert primeira["papel"] == cs.PAPEL_PROVA
    assert len(_semanas_planas(blocos)) == cs.SEMANAS_CICLO


def test_temporada_continua_cobrindo_13_semanas_sem_buraco():
    blocos = cs.esqueleto_blocos(INICIO, provas=TEMPORADA, carga_cronica=483)
    semanas = [d["semana"] for d in _semanas_planas(blocos)]

    assert len(semanas) == cs.SEMANAS_CICLO
    assert len(set(semanas)) == cs.SEMANAS_CICLO
    assert semanas == sorted(semanas)


def test_nunca_quatro_semanas_de_carga_seguidas():
    """O ritmo 3:1 é a razão de existir do ciclo — nenhum fatiamento pode furá-lo."""
    cenarios = {
        "sem prova": [],
        "temporada": TEMPORADA,
        "uma prova": [{"nome": "alvo", "data": "2026-11-29", "prioridade": "A"}],
        "pós-prova": [CARCARA],
    }
    for nome, provas in cenarios.items():
        papeis = [d["papel"] for d in
                  _semanas_planas(cs.esqueleto_blocos(INICIO, provas, 483))]
        seguidas = maior = 0
        for p in papeis:
            seguidas = seguidas + 1 if p == cs.PAPEL_CARGA else 0
            maior = max(maior, seguidas)
        assert maior <= cs.SEMANAS_CARGA_POR_BLOCO, (
            f"{nome}: {maior} semanas de carga seguidas")


def test_ciclo_de_desenvolvimento_descarrega_antes_de_aferir():
    """Medir FTP em cima de fadiga mede fadiga."""
    blocos = cs.esqueleto_blocos(INICIO, provas=TEMPORADA, carga_cronica=483)
    papeis = [d["papel"] for d in _semanas_planas(blocos)]

    assert papeis[-1] == cs.PAPEL_TESTE
    assert papeis[-2] == cs.PAPEL_DESCARGA


# ── Meta de horas × carga de referência ──────────────────────────────────────

SEMANAL_COM_MINUTOS = [
    {"semana": "2026-06-29", "tss": 523, "minutos": 445},
    {"semana": "2026-07-06", "tss": 384, "minutos": 375},
    {"semana": "2026-07-13", "tss": 478, "minutos": 439},
    {"semana": "2026-07-20", "tss": 662, "minutos": 570},
    {"semana": "2026-07-27", "tss": 488, "minutos": 406},
    {"semana": "2026-08-03", "tss": 171, "minutos": 514},
    {"semana": "2026-08-10", "tss": 0,   "minutos": 334},
    {"semana": "2026-08-17", "tss": 95,  "minutos": 316},
    {"semana": "2026-08-24", "tss": 540, "minutos": 435},
    {"semana": "2026-08-31", "tss": 387, "minutos": 900},
    {"semana": "2026-09-07", "tss": 745, "minutos": 720},
    {"semana": "2026-09-14", "tss": 0,   "minutos": 0},
]


def test_meta_de_horas_maior_puxa_a_carga_do_ciclo_para_cima():
    """Sem isto o prompt carrega duas ordens: "10h" da meta e ~9h do alvo de TSS."""
    sem_meta = cs.carga_de_referencia(SEMANAL_COM_MINUTOS)
    com_meta = cs.carga_de_referencia(SEMANAL_COM_MINUTOS, volume_alvo_min=600)
    assert com_meta > sem_meta


def test_ambicao_de_volume_vira_rampa_e_nao_salto():
    """Pedir 10-12h onde se fazia 8 é legítimo; conceder de uma vez é a lesão."""
    base = cs.carga_de_referencia(SEMANAL_COM_MINUTOS)
    absurdo = cs.carga_de_referencia(SEMANAL_COM_MINUTOS, volume_alvo_min=1500)  # 25h
    assert absurdo == round(base * cs.TETO_PROGRESSAO_CICLO)


def test_querer_treinar_menos_vale_na_hora():
    """Cortar volume é decisão dele — não precisa de rampa nem de teto."""
    base = cs.carga_de_referencia(SEMANAL_COM_MINUTOS)
    menos = cs.carga_de_referencia(SEMANAL_COM_MINUTOS, volume_alvo_min=240)  # 4h
    assert menos < base


def test_meta_de_horas_sem_historico_de_minutos_nao_quebra():
    so_tss = [{"semana": "x", "tss": 400}, {"semana": "y", "tss": 500}]
    assert cs.carga_de_referencia(so_tss, volume_alvo_min=600) == 450


def test_o_atleta_chega_na_meta_de_horas_ate_o_fim_do_ciclo():
    """A rampa tem que terminar onde ele pediu, senão é só recusar o pedido."""
    ref = cs.carga_de_referencia(SEMANAL_COM_MINUTOS, volume_alvo_min=600)
    blocos = cs.esqueleto_blocos(INICIO, provas=TEMPORADA, carga_cronica=ref)
    uteis = [s for s in SEMANAL_COM_MINUTOS if s["tss"] and s["minutos"]]
    tss_h = sum(s["tss"] for s in uteis) / (sum(s["minutos"] for s in uteis) / 60)

    pico_h = max(d["alvo_tss"] for d in _semanas_planas(blocos)) / tss_h
    assert pico_h >= 10, f"o ciclo nunca chega nas 10h pedidas (pico {pico_h:.1f}h)"


def test_cada_prova_A_da_temporada_ganha_sua_vespera_de_polimento():
    """Marcar duas etapas como A é dizer "nessas duas eu piso" — as duas polem."""
    temporada = [
        {"nome": "maratona", "data": "2026-09-27", "prioridade": "B"},
        {"nome": "XCO 1", "data": "2026-10-03", "prioridade": "A"},
        {"nome": "XCO 2", "data": "2026-10-24", "prioridade": "A"},
        {"nome": "XCM Passo Fundo", "data": "2026-11-01", "prioridade": "B"},
    ]
    blocos = cs.esqueleto_blocos(INICIO, provas=temporada, carga_cronica=524)
    det = {d["semana"]: d["papel"] for d in _semanas_planas(blocos)}

    # Véspera da 2ª XCO: semana livre vira polimento.
    assert det["2026-10-12"] == cs.PAPEL_TAPER
    # A outra semana livre segue manutenção — não se pole duas semanas seguidas.
    assert det["2026-10-05"] == cs.PAPEL_MANUTENCAO
    # E a véspera da 1ª XCO é semana de prova (maratona no dia 27): não pole correndo.
    assert det["2026-09-21"] == cs.PAPEL_PROVA


def test_vespera_de_prova_A_e_mais_leve_que_uma_semana_de_manutencao():
    temporada = [
        {"nome": "maratona", "data": "2026-09-27", "prioridade": "B"},
        {"nome": "XCO 1", "data": "2026-10-03", "prioridade": "A"},
        {"nome": "XCO 2", "data": "2026-10-24", "prioridade": "A"},
        {"nome": "XCM Passo Fundo", "data": "2026-11-01", "prioridade": "B"},
    ]
    det = {d["semana"]: d for d in
           _semanas_planas(cs.esqueleto_blocos(INICIO, temporada, 524))}
    assert det["2026-10-12"]["alvo_tss"] < det["2026-10-05"]["alvo_tss"]


def test_bloco_prompt_da_primeira_semana_de_um_ciclo_que_ainda_nao_comecou():
    """Ciclo criado no domingo para começar na segunda: olhar para ele tem que funcionar."""
    ciclo = _ciclo()
    assert cs.posicao(ciclo, "2026-09-20") is None      # domingo, véspera
    assert "BLOCO 1" in cs.bloco_prompt(ciclo, ciclo["inicio"])


# ── Ciclo × taper genérico: quem manda na semana de prova ────────────────────

def test_bloco_de_competicao_nao_repete_alvo_de_carga_do_taper():
    """Dois alvos de carga no mesmo prompt e a IA escolhe um — provavelmente o errado.

    `proxima_prova` dispara polimento para QUALQUER prova seguinte. Com quatro
    largadas em seis semanas isso poliria o atleta quatro vezes, e punha 195 TSS
    (taper) ao lado de 393 TSS (ciclo) para a mesma semana.
    """
    from app.services.plano_semana_service import _REGRAS_COMPETICAO, _REGRAS_TAPER

    assert "ALVO DE CARGA" not in _REGRAS_COMPETICAO
    assert "NÃO faça polimento completo" in _REGRAS_COMPETICAO
    # E o texto de taper de verdade continua existindo para quem não está em
    # bloco de competição.
    assert "ALVO DE CARGA DA SEMANA" in _REGRAS_TAPER["prova"] + "ALVO DE CARGA DA SEMANA"
