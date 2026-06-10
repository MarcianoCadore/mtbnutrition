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


# Item de refeição: (chave_alimento, quantidade_em_porções)
# Refeição: (nome, horario, [itens])
# Horários neutros (não assumem treino de manhã) — o treino pode ser manhã,
# tarde ou noite, então a nutrição em volta dele é guiada por NOTA_TREINO.
MENUS = {
    # ── DESCANSO ─ menor carbo, maior déficit, proteína mantida (~1950 kcal) ──
    "descanso": [
        ("Café da manhã", "09:00", [("ovo", 3), ("pao_integral", 1), ("queijo_minas", 1), ("leite_desnatado", 1)]),
        ("Lanche da manhã", "11:00", [("iogurte_natural", 1), ("whey", 1), ("banana", 1)]),
        ("Almoço", "13:00", [("arroz_integral", 1), ("feijao", 1), ("carne_bovina", 1.5), ("azeite", 1)]),
        ("Lanche da tarde", "16:30", [("whey", 1), ("pasta_amendoim", 1)]),
        ("Jantar", "20:00", [("frango", 1.5), ("batata_doce", 1), ("azeite", 1)]),
    ],
    # ── RECUPERAÇÃO ─ leve, carbo um pouco maior que descanso (~2200 kcal) ──
    "recuperacao": [
        ("Café da manhã", "09:00", [("ovo", 2), ("pao_integral", 2), ("queijo_minas", 1), ("leite_desnatado", 1)]),
        ("Lanche da manhã", "11:00", [("iogurte_natural", 1), ("whey", 1), ("banana", 1)]),
        ("Almoço", "13:00", [("arroz_branco", 1.5), ("feijao", 1), ("carne_bovina", 1.5), ("azeite", 1)]),
        ("Lanche da tarde", "16:30", [("whey", 1), ("pasta_amendoim", 1), ("banana", 1)]),
        ("Jantar", "20:00", [("frango", 1.5), ("batata_doce", 1), ("azeite", 1)]),
    ],
    # ── Z2 LONGO ─ carbo médio para o pedal longo (~2450 kcal) ──
    "z2": [
        ("Café da manhã", "09:00", [("aveia", 1), ("banana", 1), ("pao_frances", 1), ("whey", 1), ("leite_desnatado", 1)]),
        ("Lanche da manhã", "11:00", [("whey", 1), ("banana", 1), ("pao_frances", 1)]),
        ("Almoço", "13:00", [("arroz_branco", 2), ("feijao", 1), ("carne_bovina", 1.5), ("azeite", 1)]),
        ("Lanche da tarde", "16:30", [("iogurte_natural", 1), ("whey", 1), ("pasta_amendoim", 1)]),
        ("Jantar", "20:00", [("frango", 1.5), ("batata_doce", 1.5), ("azeite", 1)]),
    ],
    # ── MODERADO (TEMPO / FORÇA) ─ carbo médio-alto (~2650 kcal) ──
    "moderado": [
        ("Café da manhã", "09:00", [("aveia", 1), ("banana", 1), ("pao_frances", 1), ("ovo", 2), ("leite_desnatado", 1)]),
        ("Lanche da manhã", "11:00", [("whey", 1), ("banana", 1), ("pao_frances", 1)]),
        ("Almoço", "13:00", [("arroz_branco", 2), ("feijao", 1), ("carne_bovina", 1.5), ("azeite", 1)]),
        ("Lanche da tarde", "16:30", [("iogurte_grego", 1), ("whey", 1), ("pasta_amendoim", 1)]),
        ("Jantar", "20:00", [("frango", 1.5), ("arroz_branco", 1), ("batata_doce", 1), ("azeite", 1)]),
    ],
    # ── INTENSO (TIROS / VO2MAX) ─ carbo alto p/ alta intensidade (~3200 kcal) ──
    "intenso": [
        ("Café da manhã", "09:00", [("aveia", 1.5), ("banana", 1), ("pao_frances", 2), ("ovo", 2), ("leite_integral", 1), ("whey", 1)]),
        ("Lanche da manhã", "11:00", [("whey", 1), ("banana", 2), ("pao_frances", 1)]),
        ("Almoço", "13:00", [("arroz_branco", 2.5), ("feijao", 1), ("carne_bovina", 1.5), ("azeite", 1)]),
        ("Lanche da tarde", "16:30", [("iogurte_grego", 1), ("whey", 1), ("pasta_amendoim", 1), ("banana", 1)]),
        ("Jantar", "20:00", [("frango", 1.5), ("arroz_branco", 1), ("batata_doce", 1.5), ("azeite", 1)]),
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


def plano_para_tipo(tipo) -> dict:
    """Retorna o cardápio fixo do tipo de treino, com kcal/proteína por item,
    por refeição e total do dia."""
    if not isinstance(tipo, TipoTreino):
        try:
            tipo = TipoTreino(tipo)
        except ValueError:
            tipo = TipoTreino.DESCANSO

    menu_key = TIPO_PARA_MENU[tipo]
    refeicoes = []
    kcal_total = 0
    prot_total = 0.0

    for nome, horario, itens in MENUS[menu_key]:
        itens_exp = [_expandir_item(c, q) for c, q in itens]
        r_kcal = sum(i["kcal"] for i in itens_exp)
        r_prot = round(sum(i["proteina_g"] for i in itens_exp), 1)
        kcal_total += r_kcal
        prot_total += r_prot
        refeicoes.append({
            "nome": nome, "horario": horario,
            "kcal": r_kcal, "proteina_g": r_prot, "itens": itens_exp,
        })

    return {
        "tipo": tipo.value,
        "estrategia": ESTRATEGIA_POR_TIPO[tipo],
        "nota_treino": None if tipo == TipoTreino.DESCANSO else NOTA_TREINO,
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
