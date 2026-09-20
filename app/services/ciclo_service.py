"""Ciclo de 90 dias — a memória longa do treinador (coleção db.ciclos).

Até aqui o app decidia uma semana por vez. Isso basta para não machucar o
atleta, mas não é treinar: a semana olhava 4 semanas para trás, não sabia de
onde vinha nem para onde ia, e nenhuma decisão sobrevivia ao domingo seguinte.
O sintoma apareceu inteiro no parecer de 13/09/2026 — ACWR 1.69 com "nenhuma
semana de descarga feita no bloco". Não havia bloco. Cada semana era a primeira.

Um ciclo é o contrato de 13 semanas: onde o atleta está (`diagnostico`), o que
o segura (`limitadores`), o que o ciclo entrega (`objetivo` e `metas`), e o
caminho em blocos (`blocos`). A semana deixa de ser um evento isolado e passa
a ser a enésima semana do k-ésimo bloco de um plano que alguém pensou.

A divisão de trabalho é a mesma que já funciona no parecer fisiológico:

    O CÓDIGO é dono dos números. `esqueleto_blocos` monta a estrutura — quantos
    blocos, onde cai a descarga, quanto TSS por semana — de forma determinística
    e auditável. A descarga existe por construção, não por boa vontade do
    gerador: é isto que torna o ACWR 1.69 impossível de repetir.

    O TREINADOR é dono do julgamento. Diagnóstico, limitadores, objetivo, metas
    e racional são escritos por quem raciocina (hoje o Claude Code, via
    scripts/ciclo_claude.py), em cima do esqueleto pronto.

Formato canônico do documento:
{
    _id: ObjectId,
    user_id: str,
    numero: int,                  # 1º, 2º, ... ciclo do atleta
    inicio: "YYYY-MM-DD",         # sempre uma segunda-feira
    fim: "YYYY-MM-DD",            # domingo da 13ª semana
    estado: "ativo" | "encerrado",
    diagnostico: {                # foto de abertura — o "antes" do ciclo
        ftp, peso_kg, w_kg, carga_cronica, volume_semanal_min,
        aderencia_pct, curva_potencia: {"5s":…,"1min":…,"5min":…,"20min":…},
        gerado_em,
    },
    limitadores: [ {nome, evidencia, como_atacar, bloco_alvo} ],
    objetivo: str,
    metas: [ {chave, descricao, de, para, unidade, aferir_em} ],
    prova_alvo: {nome, data, prioridade} | None,
    blocos: [ {
        n, inicio, fim, semanas, foco, objetivo,
        semanas_detalhe: [ {semana, papel, alvo_tss} ],
        resultado: {…} | None,     # preenchido no fechamento do bloco
    } ],
    racional: str,                # a voz do treinador: por que o ciclo é assim
    criado_em, criado_por,
}
"""
import logging
from datetime import date, datetime, timedelta, timezone

from bson import ObjectId

from app.services.mongo_service import get_db
from app.utils import hoje_local

logger = logging.getLogger(__name__)

# 13 semanas = 91 dias. "90 dias" é como o atleta fala; o ciclo precisa fechar
# em semanas inteiras porque a unidade de planejamento do app é a semana.
SEMANAS_CICLO = 13

# Ritmo 3:1 — três semanas de carga e uma de descarga. É o padrão clássico de
# periodização por blocos (Issurin) e o que a literatura de carga aguda/crônica
# sustenta: sem a 4ª semana leve, o ACWR sobe sem teto e a adaptação vira dano.
SEMANAS_POR_BLOCO = 4
SEMANAS_CARGA_POR_BLOCO = 3

# Progressão de TSS DENTRO de um bloco, como fração do alvo-base do bloco.
# +8% e +7% são incrementos que cabem folgados abaixo do limiar de ACWR 1.3; a
# descarga em 0.60 é a mesma fração que o taper usa para a semana de descarga
# (prova_service._FRACAO_CARGA_TAPER), por coerência: descarregar é descarregar.
PROGRESSAO_NO_BLOCO = (1.00, 1.08, 1.15)
FRACAO_DESCARGA = 0.60

# Quanto o alvo-base sobe de um bloco para o próximo. 5% por bloco é ~16% em
# três blocos: progressão real ao longo de 90 dias sem que nenhuma semana
# isolada dê o salto que o parecer flagrou (387 → 745 TSS de uma vez).
PROGRESSAO_ENTRE_BLOCOS = 1.05

# Papéis possíveis de uma semana dentro do bloco.
PAPEL_CARGA = "carga"
PAPEL_DESCARGA = "descarga"
PAPEL_TAPER = "taper"
PAPEL_PROVA = "prova"
PAPEL_TRANSICAO = "transicao"
PAPEL_TESTE = "teste"
# Semana dentro de um bloco de competição que não tem prova: não é semana de
# construir (não dá tempo entre duas largadas) nem de descansar. É manutenção.
PAPEL_MANUTENCAO = "manutencao"

# Frações do bloco de competição. Numa temporada com provas a cada duas semanas
# não se faz taper quatro vezes — quem tenta chega mal nas quatro. O protocolo é
# mini-descarga de 2-3 dias antes de cada largada (semana ~75% da referência) e
# manutenção entre elas (~90%): a prova é o estímulo duro, o resto da semana
# sustenta a forma em vez de disputá-la com a prova.
FRACAO_SEMANA_PROVA = 0.75
FRACAO_MANUTENCAO = 0.90

# Intervalo máximo, em semanas, entre duas largadas para que elas pertençam ao
# MESMO bloco de competição. Acima disso o intervalo deixa de ser "espremido
# entre provas" e vira janela de construção de verdade (3 de carga + descarga):
# tratar duas provas distantes como uma temporada contínua condenaria o atleta a
# meses de manutenção sem construir nada.
SEMANAS_GAP_COMPETICAO = 3

# Focos de bloco. Reaproveitam o vocabulário de prova_service.FASE_LABEL para
# que portal e prompt falem a mesma língua, mais os dois que só existem aqui.
FOCO_LABEL = {
    "base": "Base aeróbica",
    "construcao": "Construção",
    "pico": "Pico",
    "taper": "Polimento (taper)",
    "transicao": "Transição / retomada",
    "afericao": "Aferição (fecha o ciclo)",
    "competicao": "Bloco de competição",
}

# Sequência padrão quando não há prova no horizonte: o ciclo é de
# desenvolvimento. Sem prova não existe pico — forçar um seria inventar uma
# data de largada que o atleta não tem.
_SEQUENCIA_SEM_PROVA = ("base", "construcao", "construcao")


# Uma prova nas semanas ANTERIORES ao início deixa resíduo: o ciclo tem que
# abrir absorvendo, não carregando. Duas semanas é a mesma janela que o taper
# usa do outro lado da prova.
SEMANAS_RESIDUO_PROVA = 2


# ── Datas ────────────────────────────────────────────────────────────────────

def segunda_de(data_iso: str) -> str:
    """Segunda-feira da semana que contém `data_iso`."""
    d = datetime.strptime(data_iso, "%Y-%m-%d").date()
    return (d - timedelta(days=d.weekday())).isoformat()


def _shift(data_iso: str, dias: int) -> str:
    d = datetime.strptime(data_iso, "%Y-%m-%d").date()
    return (d + timedelta(days=dias)).isoformat()


def _semanas_do_ciclo(inicio: str) -> list[str]:
    return [_shift(inicio, 7 * i) for i in range(SEMANAS_CICLO)]


def fim_do_ciclo(inicio: str) -> str:
    """Domingo da última semana — o ciclo fecha em semana inteira."""
    return _shift(inicio, 7 * SEMANAS_CICLO - 1)


# ── Carga de referência ──────────────────────────────────────────────────────

# Quanto a carga de referência pode subir de um ciclo para o outro. O atleta
# pede 10-12h onde vinha fazendo 8, e a ambição é legítima — mas concedê-la de
# uma vez é o salto que produz a aderência de 61%. O teto transforma o pedido
# numa rampa: ele CHEGA nas 10-12h, no fim do ciclo e não na segunda-feira.
TETO_PROGRESSAO_CICLO = 1.15


def carga_de_referencia(semanal: list[dict],
                        volume_alvo_min: int | None = None) -> int | None:
    """TSS/semana que ancora os alvos do ciclo — 12 semanas, não 4.

    O parecer semanal usa 4 semanas de propósito: ele responde "como o atleta
    está AGORA", e para isso a janela curta é a certa. Um plano de 90 dias
    responde outra pergunta — "quanto este atleta sustenta" — e herdar a janela
    curta ali produz um erro grave e silencioso: no ciclo aberto em 21/09/2026
    as 4 últimas semanas pegaram justamente o pico pré-prova (745 TSS), e o
    esqueleto saiu mandando abrir um bloco de BASE acima do maior pico
    histórico do atleta.

    MEDIANA, não média: a série real tem semanas de 745 e semanas de 0, e a
    média é puxada pelos dois extremos. Semanas com TSS zerado ficam de fora
    porque quase sempre são falta de DADO, não falta de treino — sessão
    sincronizada sem FC nem potência entra sem TSS (o app registrou 900 min e
    387 TSS numa semana, e 0 TSS em outra com 334 min). Descartar semana parada
    de verdade junto é o erro barato; incluir zeros falsos rebaixaria o alvo do
    ciclo inteiro.

    `volume_alvo_min` é a meta de horas que o atleta declarou no perfil. Quando
    ela existe, a referência deixa de ser só descritiva ("o que ele fez") e
    passa a mirar o que ele quer fazer, convertida pelo TSS/hora DELE — não por
    uma tabela — e limitada por `TETO_PROGRESSAO_CICLO`. Sem esse casamento o
    prompt carregaria duas ordens incompatíveis: "fique em 10h" da meta e "mire
    483 TSS" do ciclo, que nas horas dele são 9h2.
    """
    valores = sorted(s.get("tss") or 0 for s in (semanal or []) if (s.get("tss") or 0) > 0)
    if not valores:
        return None
    meio = len(valores) // 2
    base = float(valores[meio] if len(valores) % 2
                 else (valores[meio - 1] + valores[meio]) / 2)

    if not volume_alvo_min:
        return round(base)

    uteis = [s for s in semanal
             if (s.get("tss") or 0) > 0 and (s.get("minutos") or 0) > 0]
    if not uteis:
        return round(base)
    tss_por_hora = (sum(s["tss"] for s in uteis)
                    / (sum(s["minutos"] for s in uteis) / 60))
    ambicao = volume_alvo_min / 60 * tss_por_hora

    # Querer treinar MENOS é decisão dele e vale na hora; querer treinar mais
    # vale em rampa.
    if ambicao <= base:
        return round(ambicao)
    return round(min(ambicao, base * TETO_PROGRESSAO_CICLO))


# ── Esqueleto determinístico ─────────────────────────────────────────────────

def _alvos_do_bloco(base: float | None, papeis: list[str],
                    em_competicao: bool = False) -> list[int | None]:
    """TSS-alvo de cada semana do bloco, a partir do alvo-base.

    Sem carga crônica conhecida (atleta novo, ou semanas sem TSS medido) devolve
    None em todas: o bloco continua valendo como estrutura, e a prescrição cai
    nas regras qualitativas de sempre. Nunca inventamos um número de carga para
    quem o app ainda não mediu.
    """
    if not base or base <= 0:
        return [None] * len(papeis)
    # As frações do polimento são as do app, não outras: a semana da prova é
    # muito mais leve que uma descarga comum, e ter dois números diferentes
    # para a mesma decisão é como o taper e o ciclo acabariam discordando.
    from app.services.prova_service import _FRACAO_CARGA_TAPER

    alvos: list[int | None] = []
    i_carga = 0
    for papel in papeis:
        if papel == PAPEL_CARGA:
            fator = PROGRESSAO_NO_BLOCO[min(i_carga, len(PROGRESSAO_NO_BLOCO) - 1)]
            i_carga += 1
        elif papel == PAPEL_TAPER:
            fator = _FRACAO_CARGA_TAPER["descarga"]
        elif papel == PAPEL_PROVA:
            # Dentro de um bloco de competição a semana de prova é mais cheia
            # que um taper de verdade: não se poliria quatro vezes seguidas.
            fator = (FRACAO_SEMANA_PROVA if em_competicao
                     else _FRACAO_CARGA_TAPER["prova"])
        elif papel == PAPEL_MANUTENCAO:
            fator = FRACAO_MANUTENCAO
        elif papel in (PAPEL_DESCARGA, PAPEL_TRANSICAO):
            fator = FRACAO_DESCARGA
        elif papel == PAPEL_TESTE:
            # Semana de aferição: carga moderada para o teste sair limpo. Um
            # FTP medido em cima de fadiga acumulada mede a fadiga, não o FTP.
            fator = 0.75
        else:
            fator = FRACAO_DESCARGA
        alvos.append(round(base * fator))
    return alvos


def _papeis_de_bloco(n_semanas: int) -> list[str]:
    """Papel de cada semana de um bloco de carga: carga… e descarga no fim.

    Todo bloco de 2 semanas ou mais fecha em descarga, inclusive os curtos. A
    tentação é poupar a semana num bloco de 2 ("descarregar um bloco que mal
    começou desperdiça semana"), mas blocos encadeiam: um bloco de 2 sem fim
    emenda suas duas cargas nas do bloco seguinte e produz quatro semanas duras
    seguidas atravessando a fronteira — o ritmo 3:1 furado justamente onde
    ninguém olha, porque nenhum bloco isolado parece errado.
    """
    if n_semanas <= 1:
        return [PAPEL_CARGA] * n_semanas
    return [PAPEL_CARGA] * (n_semanas - 1) + [PAPEL_DESCARGA]


def _fatiar(n_semanas: int) -> list[int]:
    """Divide N semanas em blocos de no máximo SEMANAS_POR_BLOCO.

    A sobra vai para o PRIMEIRO bloco, não para o último: quando o ciclo é
    alinhado de trás para frente numa prova, o que precisa cair certo é o fim
    (pico e taper), e é o começo que pode ser mais curto ou mais longo.
    """
    if n_semanas <= 0:
        return []
    cheios = n_semanas // SEMANAS_POR_BLOCO
    resto = n_semanas % SEMANAS_POR_BLOCO
    if not cheios:
        return [resto]
    tamanhos = [SEMANAS_POR_BLOCO] * cheios
    if resto == 1:
        # Uma semana solta não é bloco, mas inchar outro para 5 é pior: dá
        # QUATRO semanas de carga seguidas, que é o ritmo que o 3:1 existe para
        # impedir. Desmembra em 2 na frente + 3 no fim — assim a descarga cai
        # logo antes do fechamento do ciclo, que é onde ela serve para mais
        # alguma coisa (aferir em cima de fadiga mede fadiga).
        tamanhos = [2] + tamanhos[:-1] + [SEMANAS_POR_BLOCO - 1]
    elif resto:
        tamanhos.insert(0, resto)
    return tamanhos


def _prova_recente(inicio: str, provas: list[dict] | None) -> dict | None:
    """Prova A/B nas semanas imediatamente anteriores ao início do ciclo."""
    limite = _shift(inicio, -7 * SEMANAS_RESIDUO_PROVA)
    candidatas = [
        p for p in (provas or [])
        if p.get("data") and limite <= p["data"] < inicio
        and p.get("prioridade") in ("A", "B")
    ]
    return max(candidatas, key=lambda p: p["data"]) if candidatas else None


def _maior_cluster(i_provas: list[int]) -> list[int]:
    """Maior grupo de provas próximas o bastante para ser uma temporada só.

    Duas provas separadas por mais de `SEMANAS_GAP_COMPETICAO` semanas não são
    uma temporada contínua: entre elas cabe um bloco de construção, e tratá-las
    como bloco único deixaria o atleta meses em manutenção. Empate de tamanho
    resolve pelo cluster mais cedo — é o que restringe o calendário primeiro.
    """
    if not i_provas:
        return []
    grupos: list[list[int]] = [[i_provas[0]]]
    for i in i_provas[1:]:
        if i - grupos[-1][-1] <= SEMANAS_GAP_COMPETICAO:
            grupos[-1].append(i)
        else:
            grupos.append([i])
    return max(grupos, key=lambda g: (len(g), -g[0]))


def esqueleto_blocos(
    inicio: str,
    provas: list[dict] | None = None,
    carga_cronica: float | None = None,
) -> list[dict]:
    """Monta a estrutura de blocos do ciclo — determinística e auditável.

    `provas` são as provas do atleta (formato de db.provas) que caem dentro das
    13 semanas. A de maior prioridade manda: o ciclo é alinhado DE TRÁS PARA
    FRENTE nela, porque a data da largada é a única que não se negocia. As duas
    semanas anteriores viram taper (mesma janela de prova_service), o que vem
    antes é fatiado em blocos de até 4, e o que sobra depois da prova vira
    transição.

    Sem prova no horizonte o ciclo é de desenvolvimento: base → construção →
    construção, fechando com uma semana de aferição (TESTE_FTP) que mede se os
    90 dias entregaram o que prometeram.
    """
    from app.services.prova_service import _SEMANAS_TAPER

    semanas = _semanas_do_ciclo(inicio)
    fim = fim_do_ciclo(inicio)

    # Prova-alvo: a de maior prioridade dentro da janela; empate resolve pela
    # mais próxima, que é a que restringe mais o calendário.
    candidatas = [
        p for p in (provas or [])
        if p.get("data") and inicio <= p["data"] <= fim
    ]
    alvo = None
    if candidatas:
        ordem = {"A": 0, "B": 1, "C": 2}
        alvo = sorted(
            candidatas,
            key=lambda p: (ordem.get(p.get("prioridade"), 3), p["data"]),
        )[0]

    # ── Papel de cada uma das 13 semanas ─────────────────────────────────────
    # Cada semana carrega o id do bloco a que pertence. Agrupar por FOCO seria
    # o erro óbvio: dois blocos seguidos de construção virariam um bloco único
    # de 8 semanas com uma só descarga no fim — de novo o bloco sem fim que este
    # ciclo inteiro existe para eliminar.
    papeis: list[str] = []
    focos: list[str] = []
    ids: list[int] = []

    def _empurrar(papeis_bloco: list[str], foco: str) -> None:
        bid = (ids[-1] + 1) if ids else 0
        for papel in papeis_bloco:
            papeis.append(papel)
            focos.append(foco)
            ids.append(bid)

    # Semanas do ciclo que contêm prova. Mais de uma AGRUPADA muda o modelo
    # inteiro: não se faz taper para quatro largadas em seis semanas.
    i_provas = sorted({semanas.index(segunda_de(p["data"])) for p in candidatas})
    cluster = _maior_cluster(i_provas)

    # Abre absorvendo quando o ciclo começa em cima de uma prova recém-corrida.
    # Sem isto o esqueleto manda o atleta carregar na semana seguinte à largada
    # — nenhum treinador faz isso, e é o tipo de erro que só aparece depois.
    # Não vale quando a 1ª semana já tem prova: ela já vai ser leve por isso.
    residuo = _prova_recente(inicio, provas)
    if residuo and 0 not in i_provas:
        _empurrar([PAPEL_TRANSICAO], "transicao")

    if len(cluster) >= 2:
        # ── Bloco de competição ──────────────────────────────────────────────
        # Provas agrupadas viram uma fase própria, da primeira à última largada.
        # Entre elas não há janela para construir nada (duas semanas não mudam
        # fisiologia), então a semana intermediária é de MANUTENÇÃO. O que vem
        # depois da última prova é que é o bloco de desenvolvimento de verdade.
        i0, i1 = cluster[0], cluster[-1]

        # Espaço antes da primeira largada, se houver, ainda serve para carregar.
        for k, tam in enumerate(_fatiar(max(0, i0 - len(papeis)))):
            _empurrar(_papeis_de_bloco(tam), "base" if k == 0 else "construcao")

        # Prova A dentro da temporada ganha o polimento que as B não têm: a
        # semana anterior a ela vira taper. Vale para quantas forem — marcar
        # duas etapas como A é dizer "nessas duas eu piso", e cada uma merece
        # sua véspera. A semana só não vira taper quando ela própria tem prova:
        # não se poliria correndo.
        i_alvos = {semanas.index(segunda_de(p["data"]))
                   for p in candidatas if p.get("prioridade") == "A"}

        comp = []
        for i in range(i0, i1 + 1):
            if i in cluster:
                comp.append(PAPEL_PROVA)
            elif (i + 1) in i_alvos:
                comp.append(PAPEL_TAPER)
            else:
                comp.append(PAPEL_MANUTENCAO)
        _empurrar(comp, "competicao")

        # Depois da última largada: transição e então o desenvolvimento real,
        # reservando a última semana do ciclo para a aferição.
        if i1 + 1 < SEMANAS_CICLO:
            _empurrar([PAPEL_TRANSICAO], "transicao")
        n_dev = SEMANAS_CICLO - len(papeis) - 1
        for k, tam in enumerate(_fatiar(n_dev)):
            _empurrar(_papeis_de_bloco(tam),
                      _SEQUENCIA_SEM_PROVA[min(k, len(_SEQUENCIA_SEM_PROVA) - 1)])
        if len(papeis) < SEMANAS_CICLO:
            _empurrar([PAPEL_TESTE], "afericao")
    elif alvo:
        i_prova = semanas.index(segunda_de(alvo["data"]))
        i_taper = max(0, i_prova - (_SEMANAS_TAPER - 1))
        n_antes = max(0, i_taper - len(papeis))   # desconta a transição de abertura

        # Antes do taper: blocos de carga, com foco subindo base → construção →
        # pico conforme se aproxima da prova.
        tamanhos = _fatiar(n_antes)
        escala = ["base", "construcao", "pico"]
        for k, tam in enumerate(tamanhos):
            # Os blocos finais pegam os focos mais específicos: o último antes
            # do taper é sempre o pico, o penúltimo construção, e assim por diante.
            idx_foco = len(escala) - (len(tamanhos) - k)
            foco = escala[max(0, min(idx_foco, len(escala) - 1))]
            _empurrar(_papeis_de_bloco(tam), foco)

        # Taper + dia da prova: um bloco só, e sem descarga própria — o taper
        # inteiro já é a descarga.
        _empurrar(
            [PAPEL_TAPER] * (i_prova - i_taper) + [PAPEL_PROVA],
            "taper",
        )

        # Depois da prova: transição, e o que sobrar volta a ser base.
        sobra = SEMANAS_CICLO - (i_prova + 1)
        if sobra > 0:
            _empurrar([PAPEL_TRANSICAO], "transicao")
        if sobra > 1:
            _empurrar(_papeis_de_bloco(sobra - 1), "base")
    else:
        # Ciclo de desenvolvimento: a última semana é reservada para a aferição
        # e o que sobra é fatiado em blocos de até 4 — assim a transição de
        # abertura sai do orçamento de semanas em vez de empurrar o teste
        # para fora do ciclo.
        n_carga = SEMANAS_CICLO - len(papeis) - 1
        for k, tam in enumerate(_fatiar(n_carga)):
            foco = _SEQUENCIA_SEM_PROVA[min(k, len(_SEQUENCIA_SEM_PROVA) - 1)]
            _empurrar(_papeis_de_bloco(tam), foco)
        _empurrar([PAPEL_TESTE], "afericao")

    papeis, focos, ids = papeis[:SEMANAS_CICLO], focos[:SEMANAS_CICLO], ids[:SEMANAS_CICLO]

    # Rede de segurança: prova FORA do cluster principal (uma etapa solta no meio
    # de um bloco de construção, por exemplo) não pode ser planejada como semana
    # de carga cheia. Ela não reorganiza o ciclo, mas a semana dela é dela.
    for i in i_provas:
        if i < len(papeis) and papeis[i] not in (PAPEL_PROVA, PAPEL_TAPER):
            papeis[i] = PAPEL_PROVA

    # ── Agrupa por bloco ─────────────────────────────────────────────────────
    blocos: list[dict] = []
    base = float(carga_cronica) if carga_cronica else None
    i = 0
    while i < SEMANAS_CICLO:
        j = i
        while j + 1 < SEMANAS_CICLO and ids[j + 1] == ids[i]:
            j += 1
        trecho_papeis = papeis[i:j + 1]
        alvos = _alvos_do_bloco(base, trecho_papeis, focos[i] == "competicao")
        blocos.append({
            "n":        len(blocos) + 1,
            "inicio":   semanas[i],
            "fim":      _shift(semanas[j], 6),
            "semanas":  j - i + 1,
            "foco":     focos[i],
            "objetivo": None,          # o treinador escreve em /ciclo
            "semanas_detalhe": [
                {"semana": semanas[i + k], "papel": trecho_papeis[k], "alvo_tss": alvos[k]}
                for k in range(len(trecho_papeis))
            ],
            "resultado": None,
        })
        # O alvo-base só sobe depois de um bloco que teve carga de verdade;
        # taper, transição e aferição não são degrau de progressão.
        # Competição também não é degrau: sustentar forma não é construir.
        if base and focos[i] not in ("taper", "transicao", "afericao", "competicao"):
            base *= PROGRESSAO_ENTRE_BLOCOS
        i = j + 1

    return blocos


# ── Posição do atleta dentro do ciclo ────────────────────────────────────────

def posicao(ciclo: dict | None, semana_inicio: str) -> dict | None:
    """Onde a semana `semana_inicio` cai dentro do ciclo.

    Devolve None quando não há ciclo ou a semana está fora dele — todo chamador
    precisa funcionar sem ciclo, porque atleta novo não tem um e a geração da
    semana nunca pode depender disso para acontecer.
    """
    if not ciclo:
        return None
    segunda = segunda_de(semana_inicio)
    for bloco in ciclo.get("blocos") or []:
        for k, det in enumerate(bloco.get("semanas_detalhe") or []):
            if det.get("semana") != segunda:
                continue
            todas = [
                d["semana"]
                for b in ciclo["blocos"]
                for d in (b.get("semanas_detalhe") or [])
            ]
            idx = todas.index(segunda)
            return {
                "bloco":             bloco,
                "n_bloco":           bloco["n"],
                "total_blocos":      len(ciclo["blocos"]),
                "semana_no_bloco":   k + 1,
                "semanas_no_bloco":  bloco["semanas"],
                "papel":             det.get("papel"),
                "alvo_tss":          det.get("alvo_tss"),
                "eh_descarga":       det.get("papel") in (PAPEL_DESCARGA, PAPEL_TRANSICAO),
                "semana_no_ciclo":   idx + 1,
                "semanas_restantes": len(todas) - idx - 1,
            }
    return None


# ── Banco ────────────────────────────────────────────────────────────────────

async def ciclo_ativo(user_id: str, ref: str | None = None) -> dict | None:
    """Ciclo que contém a data `ref` (padrão: hoje)."""
    dia = ref or hoje_local().isoformat()
    db = get_db()
    return await db.ciclos.find_one({
        "user_id": user_id,
        "inicio": {"$lte": dia},
        "fim": {"$gte": dia},
        "estado": "ativo",
    })


async def ciclo_ativo_ou_proximo(user_id: str, ref: str | None = None) -> dict | None:
    """O ciclo corrente ou, se ele ainda não começou, o próximo a começar.

    Um ciclo é sempre criado numa segunda-feira futura, então entre a criação e
    a virada da semana `ciclo_ativo` responde None corretamente — e quem só quer
    OLHAR o ciclo recém-criado acha que ele não foi salvo. A geração da semana
    continua usando `ciclo_ativo`, que é a pergunta certa lá: a semana pergunta
    por uma data específica, não por "o que vem por aí".
    """
    atual = await ciclo_ativo(user_id, ref)
    if atual:
        return atual
    dia = ref or hoje_local().isoformat()
    db = get_db()
    return await db.ciclos.find_one(
        {"user_id": user_id, "estado": "ativo", "inicio": {"$gt": dia}},
        sort=[("inicio", 1)],
    )


async def ciclo_por_id(ciclo_id: str) -> dict | None:
    db = get_db()
    return await db.ciclos.find_one({"_id": ObjectId(ciclo_id)})


async def listar_ciclos(user_id: str) -> list[dict]:
    db = get_db()
    cursor = db.ciclos.find({"user_id": user_id}).sort("inicio", -1)
    return [c async for c in cursor]


async def proximo_numero(user_id: str) -> int:
    db = get_db()
    ultimo = await db.ciclos.find_one({"user_id": user_id}, sort=[("numero", -1)])
    return int((ultimo or {}).get("numero") or 0) + 1


async def salvar_ciclo(user_id: str, ciclo: dict) -> dict:
    """Grava o ciclo, encerrando o anterior que ainda estiver ativo.

    Dois ciclos ativos ao mesmo tempo fariam `posicao` responder por um e o
    portal mostrar o outro — o encerramento aqui é o que garante que existe uma
    só verdade sobre "em que bloco eu estou".
    """
    db = get_db()
    await db.ciclos.update_many(
        {"user_id": user_id, "estado": "ativo"},
        {"$set": {"estado": "encerrado", "encerrado_em": datetime.now(timezone.utc)}},
    )
    doc = dict(ciclo)
    doc["user_id"] = user_id
    doc["estado"] = "ativo"
    doc.setdefault("criado_em", datetime.now(timezone.utc))
    res = await db.ciclos.insert_one(doc)
    doc["_id"] = res.inserted_id
    logger.info("Ciclo %s (%s a %s) salvo para %s",
                doc.get("numero"), doc.get("inicio"), doc.get("fim"), user_id)
    return doc


# ── Bloco de prompt ──────────────────────────────────────────────────────────

def bloco_prompt(ciclo: dict | None, semana_inicio: str) -> str:
    """O ciclo, formatado para entrar no prompt da semana.

    Sem ciclo devolve string vazia e a geração segue como sempre foi — o ciclo
    enriquece a decisão, nunca é pré-requisito dela.
    """
    pos = posicao(ciclo, semana_inicio)
    if not pos:
        return ""

    bloco = pos["bloco"]
    foco_txt = FOCO_LABEL.get(bloco["foco"], bloco["foco"])
    linhas = [
        "═══════════════════════════════════════════",
        f"CICLO DE 90 DIAS — ciclo {ciclo.get('numero', '?')} "
        f"({ciclo.get('inicio')} a {ciclo.get('fim')})",
        f"Objetivo do ciclo: {ciclo.get('objetivo') or '(não definido)'}",
        f"Você está na semana {pos['semana_no_ciclo']} de {SEMANAS_CICLO} "
        f"({pos['semanas_restantes']} restantes).",
        "",
        f"BLOCO {pos['n_bloco']} de {pos['total_blocos']} — {foco_txt} "
        f"({bloco['inicio']} a {bloco['fim']})",
        f"Semana {pos['semana_no_bloco']} de {pos['semanas_no_bloco']} do bloco "
        f"| papel desta semana: {pos['papel'].upper()}",
    ]
    if bloco.get("objetivo"):
        linhas.append(f"Objetivo do bloco: {bloco['objetivo']}")

    if pos["alvo_tss"]:
        linhas.append(
            f"ALVO DE CARGA DESTA SEMANA: ~{pos['alvo_tss']} TSS. "
            "É o número que o ciclo reservou para ela — fique perto dele. "
            "Estourar o alvo não adianta a adaptação, antecipa a fadiga."
        )

    if pos["eh_descarga"]:
        linhas.append(
            "⚠️ SEMANA DE DESCARGA — é o ponto do bloco em que a adaptação "
            "acontece. Corte volume mantendo um toque de intensidade (aberturas "
            "curtas), nada de sessão-chave, nada de longão cheio. Esta semana "
            "NÃO é para progredir: é para absorver as três anteriores. "
            "Diga isso ao atleta em \"progressao\", com estas palavras."
        )
    elif pos["papel"] == PAPEL_CARGA:
        linhas.append(
            f"Semana de CARGA {pos['semana_no_bloco']}/{pos['semanas_no_bloco'] - 1 or 1} "
            "do bloco — progrida em relação à semana anterior dentro do alvo acima."
        )
    elif pos["papel"] == PAPEL_TESTE:
        linhas.append(
            "SEMANA DE AFERIÇÃO — é o fechamento do ciclo. Inclua o TESTE_FTP e "
            "deixe a semana leve o suficiente para o teste medir forma, não fadiga."
        )
    elif pos["papel"] == PAPEL_PROVA:
        linhas.append(
            "SEMANA DE PROVA dentro do bloco de competição. A PROVA é a sessão "
            "dura da semana — não acrescente outra. Mini-descarga nos 2-3 dias "
            "anteriores (só aberturas curtas), e nada de longão cheio na véspera."
        )
    elif pos["papel"] == PAPEL_MANUTENCAO:
        linhas.append(
            "SEMANA DE MANUTENÇÃO entre duas provas. Não dá para construir "
            "fitness em duas semanas: o trabalho aqui é chegar inteiro na "
            "próxima largada. UMA sessão de qualidade, o resto em Z2, e "
            "recuperação suficiente da prova anterior."
        )

    limitadores = ciclo.get("limitadores") or []
    do_bloco = [l for l in limitadores if l.get("bloco_alvo") in (None, pos["n_bloco"])]
    if do_bloco:
        linhas.append("")
        linhas.append("LIMITADORES QUE ESTE CICLO ATACA (ataque-os nas prescrições):")
        for l in do_bloco:
            linhas.append(f"  - {l.get('nome')}: {l.get('como_atacar')}")
            if l.get("evidencia"):
                linhas.append(f"      (evidência: {l['evidencia']})")

    metas = ciclo.get("metas") or []
    if metas:
        linhas.append("")
        linhas.append("METAS DO CICLO (é contra elas que o trabalho será medido):")
        for m in metas:
            alvo = (
                f"{m.get('de')} → {m.get('para')} {m.get('unidade') or ''}".strip()
                if m.get("para") is not None else (m.get("descricao") or "")
            )
            linhas.append(f"  - {m.get('descricao') or m.get('chave')}: {alvo}")

    linhas.append("═══════════════════════════════════════════")
    return "\n".join(linhas)
