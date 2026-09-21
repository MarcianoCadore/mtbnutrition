"""A série principal define o tipo — menção incidental de zona não define.

Bug real, 21/09/2026: o envio pro Garmin dispara `_reclassificar_impl`, que
reescreve o tipo de cada treino a partir da descrição. Um treino de limiar de
"2x10 min em Z3" foi rebaixado para Z2_LONGO, e o card passou a anunciar Z2 com
uma prescrição de limiar dentro.

Duas causas somadas, as duas corrigidas aqui:

1. "cadência" pontuava para Z2_LONGO. Toda prescrição bem escrita traz alvo de
   cadência — VO2máx e limiar inclusive — então ela não distinguia nada e
   empurrava tudo para Z2. Pior: o ciclo de 90 dias EXIGE alvo de cadência em
   todo treino (limitador de giro baixo), de modo que seguir a orientação do
   treinador quebrava o classificador.

2. Só existia detector de série principal para Z5. Blocos de minutos em Z3/Z4
   caíam no scorer por palavras-chave, onde o "Z1 a Z2" do aquecimento e o "Z1"
   da volta à calma somavam mais que o único trecho que define o treino.
"""
from app.services.ai_service import classificar_por_texto, tipo_definitivo

TEMPO_REAL = """A ÚNICA abertura de intensidade da semana — curta, em watts, na bike com potenciômetro.

ESTRUTURA:
- 20 min de aquecimento progressivo de Z1 a Z2
- 2x10 min em Z3 (ritmo de maratona), 5 min soltos em Z1 entre eles — segure o watt-alvo da legenda, cadência 90-95 rpm
- 20 min de volta à calma em Z1

É ritmo de prova de 60 km, não é tiro."""


def test_o_bug_real_de_24_09_serie_de_z3_nao_vira_z2():
    assert classificar_por_texto(TEMPO_REAL) == "TEMPO"


def test_serie_de_minutos_em_z3_ou_z4_e_limiar():
    for texto in ("3x10 min em Z3 com 5 min soltos em Z1 entre os blocos",
                  "4x8 minutos em Z4, recuperação de 4 min em Z1",
                  "2 × 20 min em Z3 no meio do longão"):
        assert tipo_definitivo(texto) == "TEMPO", texto


def test_aquecimento_e_volta_a_calma_nao_definem_o_treino():
    """O erro era este: Z1/Z2 incidentais afogando a série principal."""
    texto = ("Aquecimento 25 min de Z1 a Z2. 3x12 min em Z4, 5 min em Z1 entre "
             "eles. Volta à calma 20 min em Z1 e Z2.")
    assert classificar_por_texto(texto) == "TEMPO"


def test_alvo_de_cadencia_nao_transforma_o_treino_em_z2():
    """O ciclo manda pôr cadência em TODO treino — não pode quebrar o tipo."""
    texto = ("Aquecimento 20 min Z1-Z2. 5x4 min em Z5 com 4 min soltos em Z1. "
             "Cadência 95-105 rpm nos blocos. Volta à calma 15 min Z1.")
    assert classificar_por_texto(texto) == "VO2MAX"

    limiar = ("Aquecimento 20 min. 3x10 min em Z3 segurando o watt-alvo, "
              "cadência 90-95 rpm. Volta à calma em Z1.")
    assert classificar_por_texto(limiar) == "TEMPO"


def test_abertura_de_segundos_em_z4_e_ativacao_nao_limiar():
    """Três piques de 90 s na véspera da prova não são treino de limiar.

    Carimbar TEMPO aqui mandava alvo de limiar para o relógio no dia anterior
    à largada.
    """
    vespera = ("Ativação da véspera. 90 min soltos. 30 min em Z1 subindo para "
               "Z2. 3 aberturas de 90s em Z4, com 4 min soltos entre elas. "
               "Restante em Z1/Z2 solto.")
    assert classificar_por_texto(vespera) != "TEMPO"


def test_z5_continua_mandando_mais_que_z3_na_mesma_sessao():
    """Sessão mista: quem define o dia é o estímulo mais duro."""
    texto = "Aquecimento 15 min. 4x4 min em Z5, depois 2x10 min em Z3. Volta à calma."
    assert classificar_por_texto(texto) == "VO2MAX"


def test_os_tipos_classicos_nao_regridem():
    casos = [
        ("Aquecimento 20 min Z1-Z2. 5x4 min em Z5 com 4 min de recuperação em Z1. "
         "Volta à calma 15 min Z1.", "VO2MAX"),
        ("Aquecimento 20 min Z2. 8x30 s em Z5 all-out, 4 min soltos em Z1 entre eles.",
         "TIROS"),
        ("Recuperação ativa em terreno plano. 60 min soltos em Z1, cadência 90-100 rpm.",
         "RECUPERACAO"),
        ("Longão de 180 min em Z2, base aeróbica, ritmo livre.", "Z2_LONGO"),
    ]
    for texto, esperado in casos:
        assert classificar_por_texto(texto) == esperado, texto


def test_sem_serie_clara_o_scorer_continua_decidindo():
    assert tipo_definitivo("pedal solto de 1h") is None
    assert classificar_por_texto("Longão em Z2, base aeróbica") == "Z2_LONGO"
