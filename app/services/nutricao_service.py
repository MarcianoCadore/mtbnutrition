"""
Planos alimentares fixos por tipo de treino — orientados ao objetivo
"perder peso mantendo a potência" (melhorar W/kg).

Estratégia nutricional (fuel for the work required):
  • Déficit calórico MODERADO — agressivo demais derruba a potência.
  • Proteína ALTA e constante (~1,8–2,2 g/kg) — preserva músculo no déficit.
  • Carboidrato PERIODIZADO — mais nos dias de treino forte/longo (combustível
    e recuperação), menos nos dias leves e de descanso (aprofunda o déficit).

Tudo é calculado a partir de uma tabela de alimentos básicos, então o total de
kcal/proteína de cada refeição é transparente ("calorias por alimento").

Perfil: Marciano, 85 kg → meta 78 kg, 1,81 m, 34 anos. Meta proteína ~187 g/dia.
"""
import re
from datetime import date

from app.models.models import TipoTreino

# ─────────────────────────────────────────────────────────────────────────────
# Tabela de alimentos básicos — valores por porção-base indicada.
#   kcal e prot (proteína em g) referem-se a 1 porção-base.
# ─────────────────────────────────────────────────────────────────────────────
ALIMENTOS = {
    # carboidratos
    "aveia":          {"nome": "Aveia em flocos",     "base": "40 g (4 col. sopa)", "kcal": 150, "prot": 5.0},
    "pao_frances":    {"nome": "Pão francês",          "base": "1 unidade (50 g)",   "kcal": 140, "prot": 4.0},
    "pao_integral":   {"nome": "Pão integral",         "base": "1 fatia (25 g)",     "kcal": 65,  "prot": 3.0},
    "arroz_branco":   {"nome": "Arroz branco cozido",  "base": "100 g (4 col. sopa)","kcal": 130, "prot": 2.7},
    "arroz_integral": {"nome": "Arroz integral cozido","base": "100 g (4 col. sopa)","kcal": 124, "prot": 2.6},
    "feijao":         {"nome": "Feijão cozido",        "base": "100 g (1 concha)",   "kcal": 76,  "prot": 5.0},
    "batata_doce":    {"nome": "Batata-doce cozida",   "base": "100 g",              "kcal": 86,  "prot": 1.6},
    "banana":         {"nome": "Banana",               "base": "1 unidade",          "kcal": 90,  "prot": 1.2},
    # proteínas
    "ovo":            {"nome": "Ovo",                  "base": "1 unidade",          "kcal": 72,  "prot": 6.0},
    "carne_bovina":   {"nome": "Carne bovina magra (patinho)", "base": "100 g grelhada", "kcal": 190, "prot": 32.0},
    "frango":         {"nome": "Peito de frango",      "base": "100 g grelhado",     "kcal": 165, "prot": 31.0},
    "whey":           {"nome": "Whey protein",         "base": "1 scoop (30 g)",     "kcal": 120, "prot": 24.0},
    # laticínios
    "leite_desnatado":{"nome": "Leite desnatado",      "base": "200 ml (1 copo)",    "kcal": 70,  "prot": 7.0},
    "leite_integral": {"nome": "Leite integral",       "base": "200 ml (1 copo)",    "kcal": 120, "prot": 6.0},
    "iogurte_natural":{"nome": "Iogurte natural",      "base": "170 g (1 pote)",     "kcal": 100, "prot": 10.0},
    "iogurte_grego":  {"nome": "Iogurte grego",        "base": "130 g",              "kcal": 120, "prot": 11.0},
    "queijo_minas":   {"nome": "Queijo minas",         "base": "1 fatia (30 g)",     "kcal": 80,  "prot": 5.0},
    "queijo_mussarela":{"nome": "Queijo mussarela",    "base": "1 fatia (20 g)",     "kcal": 60,  "prot": 4.5},
    # gorduras boas
    "azeite":         {"nome": "Azeite de oliva",      "base": "1 col. sopa",        "kcal": 90,  "prot": 0.0},
    "pasta_amendoim": {"nome": "Pasta de amendoim",    "base": "1 col. sopa",        "kcal": 95,  "prot": 4.0},
}


_PLURAIS = {
    "unidade": "unidades", "fatia": "fatias", "scoop": "scoops",
    "copo": "copos", "concha": "conchas", "pote": "potes",
}


def _qtd_label(qtd: float, base: str) -> str:
    """Multiplica a porção-base de forma legível, escalando todos os números e
    pluralizando as unidades: 2 × '1 unidade (50 g)' → '2 unidades (100 g)'."""
    if qtd == 1:
        return base

    def _scale(m: re.Match) -> str:
        v = float(m.group()) * qtd
        return str(int(v)) if v == int(v) else f"{v:.1f}"

    out = re.sub(r"\d+(?:\.\d+)?", _scale, base)
    if qtd > 1:
        for sing, plur in _PLURAIS.items():
            out = re.sub(rf"\b{sing}\b", plur, out)
    return out


# ── Grupos de substituição ─ alternativas com calorias parecidas. ───────────
# O cardápio escolhe UMA alternativa por slot a cada dia (variando pela data),
# então o menu muda diariamente sem sair da meta calórica.
# Estrutura: slot = lista de alternativas; alternativa = lista de (alimento, qtd).
G_PROT_MAIN   = [[("carne_bovina", 1.5)], [("frango", 1.7)], [("ovo", 4)]]            # ~285 / 281 / 288 kcal
G_CARB_1      = [[("arroz_branco", 1)], [("arroz_integral", 1)], [("batata_doce", 1.5)]]   # ~130
G_CARB_15     = [[("arroz_branco", 1.5)], [("arroz_integral", 1.5)], [("batata_doce", 2)]] # ~186-195
G_CARB_2      = [[("arroz_branco", 2)], [("arroz_integral", 2)], [("batata_doce", 3)]]      # ~260
G_CARB_25     = [[("arroz_branco", 2.5)], [("arroz_integral", 2.5)], [("batata_doce", 3.5)]]# ~310-325
G_CARB_CAFE   = [[("aveia", 1)], [("pao_frances", 1)], [("pao_integral", 2)]]               # ~130-150
G_CARB_CAFE15 = [[("aveia", 1.5)], [("pao_frances", 2)], [("pao_integral", 3)]]             # ~195-280
G_LANCHE      = [[("whey", 1)], [("iogurte_grego", 1)]]                                     # ~120
G_LANCHE2     = [[("whey", 1)], [("iogurte_natural", 1)]]                                   # ~100-120
FIX = lambda *itens: [list(itens)]   # slot de alternativa única (item fixo)

# Refeição: (nome, horario, [slot, slot, ...]); slot = lista de alternativas.
# Horários neutros (não assumem treino de manhã) — o treino pode ser manhã,
# tarde ou noite, então a nutrição em volta dele é guiada por NOTA_TREINO.
MENUS = {
    # ── DESCANSO ─ menor carbo, maior déficit, proteína mantida (~1950 kcal) ──
    "descanso": [
        ("Café da manhã", "09:00", [FIX(("ovo", 3)), FIX(("pao_integral", 1)), FIX(("queijo_minas", 1)), FIX(("leite_desnatado", 1)), FIX(("iogurte_natural", 1)), G_LANCHE]),
        ("Lanche da manhã", "10:30", [FIX(("banana", 1)), G_LANCHE]),
        ("Almoço", "13:00", [G_CARB_1, FIX(("feijao", 1)), G_PROT_MAIN, FIX(("azeite", 1)), FIX(("banana", 1))]),
        ("Lanche da tarde", "16:30", [G_LANCHE, FIX(("pasta_amendoim", 1))]),
        ("Jantar", "20:00", [G_PROT_MAIN, G_CARB_1, FIX(("azeite", 1))]),
    ],
    # ── RECUPERAÇÃO ─ leve, carbo um pouco maior que descanso (~2200 kcal) ──
    "recuperacao": [
        ("Café da manhã", "09:00", [FIX(("ovo", 2)), FIX(("pao_integral", 2)), FIX(("queijo_minas", 1)), FIX(("leite_desnatado", 1)), FIX(("iogurte_natural", 1)), G_LANCHE]),
        ("Lanche da manhã", "10:30", [FIX(("banana", 1)), G_LANCHE]),
        ("Almoço", "13:00", [G_CARB_15, FIX(("feijao", 1)), G_PROT_MAIN, FIX(("azeite", 1)), FIX(("banana", 1))]),
        ("Lanche da tarde", "16:30", [G_LANCHE, FIX(("pasta_amendoim", 1)), FIX(("banana", 1))]),
        ("Jantar", "20:00", [G_PROT_MAIN, G_CARB_1, FIX(("azeite", 1))]),
    ],
    # ── Z2 LONGO ─ carbo médio para o pedal longo (~2450 kcal) ──
    "z2": [
        ("Café da manhã", "09:00", [G_CARB_CAFE, FIX(("banana", 1)), FIX(("pao_frances", 2)), FIX(("whey", 1)), FIX(("leite_desnatado", 1)), G_LANCHE]),
        ("Lanche da manhã", "10:30", [FIX(("banana", 1)), G_LANCHE]),
        ("Almoço", "13:00", [G_CARB_2, FIX(("feijao", 1)), G_PROT_MAIN, FIX(("azeite", 1)), FIX(("banana", 1))]),
        ("Lanche da tarde", "16:30", [FIX(("iogurte_natural", 1)), G_LANCHE, FIX(("pasta_amendoim", 1))]),
        ("Jantar", "20:00", [G_PROT_MAIN, G_CARB_15, FIX(("azeite", 1))]),
    ],
    # ── MODERADO (TEMPO / FORÇA) ─ carbo médio-alto (~2650 kcal) ──
    "moderado": [
        ("Café da manhã", "09:00", [G_CARB_CAFE, FIX(("banana", 1)), FIX(("pao_frances", 2)), FIX(("ovo", 2)), FIX(("leite_desnatado", 1)), G_LANCHE]),
        ("Lanche da manhã", "10:30", [FIX(("banana", 1)), G_LANCHE]),
        ("Almoço", "13:00", [G_CARB_2, FIX(("feijao", 1)), G_PROT_MAIN, FIX(("azeite", 1)), FIX(("banana", 1))]),
        ("Lanche da tarde", "16:30", [FIX(("iogurte_grego", 1)), G_LANCHE2, FIX(("pasta_amendoim", 1))]),
        ("Jantar", "20:00", [G_PROT_MAIN, G_CARB_1, FIX(("batata_doce", 1)), FIX(("azeite", 1))]),
    ],
    # ── INTENSO (TIROS / VO2MAX) ─ carbo alto p/ alta intensidade (~3200 kcal) ──
    "intenso": [
        ("Café da manhã", "09:00", [G_CARB_CAFE15, FIX(("banana", 1)), FIX(("pao_frances", 3)), FIX(("ovo", 2)), FIX(("leite_integral", 1)), FIX(("whey", 1)), G_LANCHE]),
        ("Lanche da manhã", "10:30", [FIX(("banana", 2)), G_LANCHE]),
        ("Almoço", "13:00", [G_CARB_25, FIX(("feijao", 1)), G_PROT_MAIN, FIX(("azeite", 1)), FIX(("banana", 2))]),
        ("Lanche da tarde", "16:30", [FIX(("iogurte_grego", 1)), G_LANCHE2, FIX(("pasta_amendoim", 1)), FIX(("banana", 1))]),
        ("Jantar", "20:00", [G_PROT_MAIN, FIX(("arroz_branco", 1)), G_CARB_15, FIX(("azeite", 1))]),
    ],
}

# Orientação de nutrição ao redor do treino — válida em qualquer horário
# (manhã, tarde ou noite), já que o treino não tem hora fixa.
NOTA_TREINO = (
    "Treino em horário variável (manhã/tarde/noite): ~1h ANTES do treino, "
    "puxe o carboidrato da refeição mais próxima (pão, banana, aveia ou arroz). "
    "LOGO APÓS o treino, tome o whey + uma fruta ou pão para repor. "
    "Mantenha as outras refeições normais nos horários acima."
)

# Cada tipo de treino aponta para um cardápio e tem uma orientação própria.
TIPO_PARA_MENU = {
    TipoTreino.DESCANSO:    "descanso",
    TipoTreino.RECUPERACAO: "recuperacao",
    TipoTreino.Z2_LONGO:    "z2",
    TipoTreino.TEMPO:       "moderado",
    TipoTreino.FORCA:       "moderado",
    TipoTreino.TIROS:       "intenso",
    TipoTreino.VO2MAX:      "intenso",
}

ESTRATEGIA_POR_TIPO = {
    TipoTreino.DESCANSO:    "Dia sem treino: menos carboidrato e maior déficit. Proteína mantida alta para preservar músculo. Capriche em verduras à vontade.",
    TipoTreino.RECUPERACAO: "Pedal leve/regenerativo: carboidrato baixo-moderado. Foco em recuperar sem encher o tanque — o gasto é pequeno.",
    TipoTreino.Z2_LONGO:    "Pedal longo aeróbico: carregue carboidrato no café (pré) e logo após o treino para repor o glicogênio gasto nas horas de Z2.",
    TipoTreino.TEMPO:       "Esforço de limiar/sweet spot: carboidrato médio-alto, concentrado em volta do treino. Proteína alta para a recuperação muscular.",
    TipoTreino.FORCA:       "Força/torque: prioridade na proteína para o estímulo de força, com carboidrato médio-alto para sustentar a sessão pesada.",
    TipoTreino.TIROS:       "Alta intensidade: o corpo queima muito carboidrato. Encha o tanque antes (café) e reponha bem depois — sem isso a potência cai.",
    TipoTreino.VO2MAX:      "VO2máx: máxima demanda de carboidrato. Pré-treino reforçado e reposição imediata no pós para aguentar os esforços máximos.",
}


def _expandir_item(chave: str, qtd: float) -> dict:
    a = ALIMENTOS[chave]
    kcal = round(a["kcal"] * qtd)
    prot = round(a["prot"] * qtd, 1)
    return {"texto": f"{_qtd_label(qtd, a['base'])} — {a['nome']}", "kcal": kcal, "proteina_g": prot}


# Horários padrão das refeições (configuráveis pelo usuário em db.config).
DEFAULT_HORARIOS = {"cafe": "09:00", "lanche_manha": "10:30", "almoco": "13:00", "lanche_tarde": "16:30", "jantar": "20:00"}


def horarios_por_refeicao(cfg: dict | None = None) -> dict:
    """Mapeia cada refeição ao horário configurado (5 refeições)."""
    c = {**DEFAULT_HORARIOS, **(cfg or {})}
    return {
        "Café da manhã":   c["cafe"],
        "Lanche da manhã": c["lanche_manha"],
        "Almoço":          c["almoco"],
        "Lanche da tarde": c["lanche_tarde"],
        "Jantar":          c["jantar"],
    }


# ── Período do treino no dia ────────────────────────────────────────────────
# O usuário escolhe, por dia, quando vai treinar. A nutrição concentra o
# carboidrato em volta do treino: reforça o pré e marca o pós para reposição,
# tirando uma porção de carbo de uma refeição longe do treino (mantém ~o total).
PERIODO_FRASE = {"manha": "de manhã", "meio_dia": "ao meio-dia", "tarde": "à tarde", "noite": "à noite"}

# período -> (refeição pré-treino [+carbo], pós-treino [reposição], doadora do carbo)
PERIODO_REFEICOES = {
    "manha":    ("Café da manhã",   "Lanche da manhã", "Jantar"),
    "meio_dia": ("Lanche da manhã", "Almoço",          "Jantar"),
    "tarde":    ("Almoço",          "Lanche da tarde", "Café da manhã"),
    "noite":    ("Lanche da tarde", "Jantar",          "Café da manhã"),
}

# carboidratos que podem ser movidos entre refeições (1 porção).
_CARBO_MOVEL = ("banana", "arroz_branco", "arroz_integral", "batata_doce",
                "pao_frances", "pao_integral", "aveia")


def _aplicar_periodo(refeicoes_raw: list[dict], periodo: str) -> None:
    """Redistribui o carboidrato em volta do treino (edita refeicoes_raw in place).
    Tira 1 porção de carbo da refeição doadora e concentra carbo rápido (banana)
    na pré-treino; marca pré e pós com a observação correspondente."""
    pre_nome, pos_nome, doador_nome = PERIODO_REFEICOES[periodo]
    por_nome = {r["nome"]: r for r in refeicoes_raw}
    doador, pre, pos = por_nome.get(doador_nome), por_nome.get(pre_nome), por_nome.get(pos_nome)

    if doador:
        for idx, (chave, qtd) in enumerate(doador["itens"]):
            if chave in _CARBO_MOVEL:
                if qtd > 1:
                    doador["itens"][idx] = (chave, qtd - 1)
                else:
                    doador["itens"].pop(idx)
                break

    if pre is not None:
        pre["itens"].append(("banana", 1))
        pre["observacao"] = "⚡ Pré-treino: carbo reforçado pra energia (treino logo após)."
    if pos is not None:
        pos["observacao"] = "🔋 Pós-treino: capriche na proteína (whey/iogurte) + uma fruta pra repor."


def periodo_de_hora(hora: int) -> str:
    """Mapeia a hora (0-23) em que o treino foi feito para o período do dia."""
    if 5 <= hora < 11:
        return "manha"
    if 11 <= hora < 14:
        return "meio_dia"
    if 14 <= hora < 18:
        return "tarde"
    return "noite"


def nota_treino_periodo(periodo: str, horarios: dict) -> str:
    """Orientação específica do período, citando as refeições pré/pós reais."""
    pre_nome, pos_nome, _ = PERIODO_REFEICOES[periodo]
    return (
        f"Treino {PERIODO_FRASE[periodo]}: ~1h ANTES reforce o carboidrato do "
        f"{pre_nome} ({horarios.get(pre_nome, '')}). LOGO APÓS, reponha no "
        f"{pos_nome} ({horarios.get(pos_nome, '')}) com proteína + uma fruta."
    )


def _seed(data_iso: str | None) -> int:
    """Semente determinística a partir da data (dias diferentes → menus diferentes)."""
    if not data_iso:
        return 0
    try:
        return date.fromisoformat(data_iso[:10]).toordinal()
    except ValueError:
        return 0


def plano_para_tipo(tipo, data_iso: str | None = None, horarios_cfg: dict | None = None,
                    periodo: str | None = None) -> dict:
    """Monta o cardápio do tipo de treino para uma data, com kcal/proteína por
    item, por refeição e total do dia.

    A cada dia escolhe uma combinação diferente de alternativas (variando pela
    data), mantendo as calorias-alvo. Sem data, usa um exemplo estável.
    Os horários das refeições vêm de horarios_cfg (config do usuário).

    Se 'periodo' for informado (manha/meio_dia/tarde/noite), redistribui o
    carboidrato em volta do treino (reforça o pré, marca o pós) sem mudar o tipo.
    """
    if not isinstance(tipo, TipoTreino):
        try:
            tipo = TipoTreino(tipo)
        except ValueError:
            tipo = TipoTreino.DESCANSO

    menu_key = TIPO_PARA_MENU[tipo]
    seed = _seed(data_iso)
    horarios = horarios_por_refeicao(horarios_cfg)

    # 1) escolhe as alternativas de cada slot (ainda como (chave, qtd))
    pos = 0
    refeicoes_raw = []
    for nome, horario_padrao, slots in MENUS[menu_key]:
        escolhidos = []
        for slot in slots:
            alt = slot[(seed + pos) % len(slot)]   # escolhe 1 alternativa do slot
            pos += 1
            escolhidos.extend(alt)
        refeicoes_raw.append({
            "nome": nome, "horario": horarios.get(nome, horario_padrao),
            "itens": list(escolhidos), "observacao": None,
        })

    # 2) com treino e período definido, redistribui o carbo em volta do treino
    aplicar = periodo in PERIODO_REFEICOES and tipo != TipoTreino.DESCANSO
    if aplicar:
        _aplicar_periodo(refeicoes_raw, periodo)

    # 3) expande os itens e soma kcal/proteína
    refeicoes = []
    kcal_total = 0
    prot_total = 0.0
    for r in refeicoes_raw:
        itens_exp = [_expandir_item(chave, qtd) for chave, qtd in r["itens"]]
        r_kcal = sum(i["kcal"] for i in itens_exp)
        r_prot = round(sum(i["proteina_g"] for i in itens_exp), 1)
        kcal_total += r_kcal
        prot_total += r_prot
        refeicoes.append({
            "nome": r["nome"], "horario": r["horario"],
            "kcal": r_kcal, "proteina_g": r_prot, "itens": itens_exp,
            "observacao": r["observacao"],
        })

    if tipo == TipoTreino.DESCANSO:
        nota = None
    elif aplicar:
        nota = nota_treino_periodo(periodo, horarios)
    else:
        nota = NOTA_TREINO

    return {
        "tipo": tipo.value,
        "periodo": periodo if aplicar else None,
        "estrategia": ESTRATEGIA_POR_TIPO[tipo],
        "nota_treino": nota,
        "kcal_total": kcal_total,
        "proteina_total_g": round(prot_total, 1),
        "refeicoes": refeicoes,
    }


def tabela_alimentos() -> list[dict]:
    """Lista a tabela de alimentos básicos para a página de referência."""
    return [
        {"nome": a["nome"], "base": a["base"], "kcal": a["kcal"], "prot": a["prot"]}
        for a in ALIMENTOS.values()
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Guia "o que comer em cada refeição" — organizado por refeição (não por treino).
#   Ensina quando comer cada alimento, com as calorias por porção.
# ─────────────────────────────────────────────────────────────────────────────
REFEICOES_GUIA = [
    {
        "nome": "Café da manhã",
        "horario": "09:00",
        "papel": "Abre o dia com carboidrato + proteína. O carboidrato dá energia "
                 "e a proteína segura a fome até o almoço.",
        "alimentos": ["aveia", "pao_frances", "pao_integral", "ovo",
                      "leite_desnatado", "queijo_minas", "whey", "banana"],
        "dica": "Se for treinar de manhã, reforce o carboidrato (aveia, pão ou banana) "
                "~1h antes. Se o treino for à tarde/noite, mantenha o café normal.",
    },
    {
        "nome": "Lanche da manhã",
        "horario": "10:30",
        "papel": "Ponte entre o café e o almoço: uma fruta para energia rápida e "
                 "proteína (whey ou iogurte) para segurar a fome sem pesar.",
        "alimentos": ["banana", "whey", "iogurte_grego", "iogurte_natural"],
        "dica": "Se o treino for de manhã, este é um ótimo momento para repor logo "
                "após: whey + banana caem bem no pós-treino.",
    },
    {
        "nome": "Almoço",
        "horario": "13:00",
        "papel": "Refeição principal: carboidrato (energia), proteína magra (músculo) "
                 "e feijão + salada à vontade (saciedade e fibras).",
        "alimentos": ["arroz_branco", "arroz_integral", "feijao",
                      "carne_bovina", "frango", "azeite"],
        "dica": "Encha metade do prato de salada/legumes, um quarto de proteína e um "
                "quarto de arroz+feijão. Salada e verduras são livres.",
    },
    {
        "nome": "Lanche da tarde",
        "horario": "16:30",
        "papel": "Mantém a proteína ao longo do dia e evita chegar faminto no jantar. "
                 "Proteína + uma fruta ou gordura boa.",
        "alimentos": ["iogurte_natural", "iogurte_grego", "whey",
                      "banana", "pasta_amendoim", "queijo_mussarela"],
        "dica": "Ótimo momento para o whey se você não usou no café. Pasta de amendoim "
                "com moderação (1 colher) — é calórica.",
    },
    {
        "nome": "Jantar (noite)",
        "horario": "20:00",
        "papel": "Mais leve que o almoço: proteína para a recuperação noturna e "
                 "carboidrato moderado (batata-doce ou um pouco de arroz).",
        "alimentos": ["frango", "carne_bovina", "ovo",
                      "batata_doce", "arroz_branco", "azeite"],
        "dica": "À noite o gasto é menor: segure o carboidrato, mas não corte a "
                "proteína. Legumes e verduras à vontade.",
    },
]


_TIPO_LABEL_WPP = {
    "Z2_LONGO": "🚴 Z2 Longo", "TIROS": "⚡ Tiros", "VO2MAX": "🔥 VO2Max",
    "TEMPO": "💨 Tempo", "FORCA": "💪 Força", "RECUPERACAO": "🌿 Recuperação",
    "DESCANSO": "🛌 Descanso",
}


def formatar_plano_whatsapp(data_iso: str, plano: dict) -> str:
    """Monta a mensagem do plano alimentar do dia para o WhatsApp."""
    from datetime import datetime
    d = datetime.strptime(data_iso, "%Y-%m-%d")
    dias = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    data_fmt = d.strftime("%d/%m/%Y")
    tipo_lbl = _TIPO_LABEL_WPP.get(plano["tipo"], plano["tipo"])

    linhas = [
        f"🍽️ *Plano alimentar — {dias[d.weekday()]}, {data_fmt}*",
        f"{tipo_lbl} · {plano['kcal_total']} kcal · {plano['proteina_total_g']:g}g proteína",
        "",
        f"💡 _{plano['estrategia']}_",
    ]
    if plano.get("nota_treino"):
        linhas += ["", f"⏰ {plano['nota_treino']}"]
    linhas.append("")

    for r in plano["refeicoes"]:
        linhas.append(f"*{r['horario']} · {r['nome']}* ({r['kcal']} kcal · {r['proteina_g']:g}g P)")
        for i in r["itens"]:
            linhas.append(f"  • {i['texto']}")
        if r.get("observacao"):
            linhas.append(f"  {r['observacao']}")
        linhas.append("")

    linhas.append("💧 Mínimo 3L de água/dia")
    linhas.append("_MTB Nutrition Bot 🤖_")
    return "\n".join(linhas)


def formatar_lembrete_refeicao(ref: dict) -> str:
    """Mensagem de lembrete (30 min antes) com o que comer na refeição."""
    linhas = [
        f"⏰ *Daqui a 30 min — {ref['nome']} ({ref['horario']})*",
    ]
    if ref.get("observacao"):
        linhas += ["", ref["observacao"]]
    linhas += ["", "🍽️ O que comer:"]
    for i in ref["itens"]:
        linhas.append(f"  • {i['texto']}")
    linhas += ["", f"_{ref['kcal']} kcal · {ref['proteina_g']:g}g proteína_", "_MTB Nutrition Bot 🤖_"]
    return "\n".join(linhas)


def guia_refeicoes() -> list[dict]:
    """Expande o guia por refeição com kcal/proteína por alimento recomendado."""
    out = []
    for r in REFEICOES_GUIA:
        alimentos = [
            {"nome": ALIMENTOS[k]["nome"], "base": ALIMENTOS[k]["base"],
             "kcal": ALIMENTOS[k]["kcal"], "prot": ALIMENTOS[k]["prot"]}
            for k in r["alimentos"]
        ]
        out.append({**r, "alimentos": alimentos})
    return out
