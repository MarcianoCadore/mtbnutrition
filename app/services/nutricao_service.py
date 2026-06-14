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

Perfil: Marciano, 84 kg → meta < 80 kg (melhorar W/kg p/ subir mais rápido),
1,81 m, 35 anos. Meta proteína ~170 g/dia. 4 refeições/dia (sem lanche da manhã),
no máx. 2 scoops de whey/dia.
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
    "tilapia":        {"nome": "Filé de tilápia",      "base": "100 g grelhado",     "kcal": 130, "prot": 26.0},
    "linguica":       {"nome": "Linguiça grelhada",    "base": "100 g (2 gomos)",    "kcal": 290, "prot": 16.0},
    "whey":           {"nome": "Whey protein",         "base": "1 scoop (30 g)",     "kcal": 120, "prot": 24.0},
    # laticínios
    "leite_desnatado":{"nome": "Leite desnatado",      "base": "200 ml (1 copo)",    "kcal": 70,  "prot": 7.0},
    "leite_integral": {"nome": "Leite integral",       "base": "200 ml (1 copo)",    "kcal": 120, "prot": 6.0},
    "cafe_com_leite": {"nome": "Café com leite (sem açúcar)", "base": "1 xícara (200 ml)", "kcal": 110, "prot": 6.5},
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
PROT_ALMOCO = [[("frango", 1.5)], [("carne_bovina", 1.5)], [("tilapia", 1.8)]]  # ~234-285 · 46-48g P
PROT_JANTAR = [[("frango", 1.3)], [("carne_bovina", 1.2)], [("tilapia", 1.5)]]  # ~195-228 · 38-40g P
LEITE       = [[("cafe_com_leite", 1)], [("leite_desnatado", 1)], [("iogurte_natural", 1)]]  # bebida do café (rodízio)
CAFE_CARB   = [[("aveia", 1)], [("pao_frances", 1)], [("pao_integral", 2)]]   # ~130-150
G_CARB_1    = [[("arroz_branco", 1)],   [("arroz_integral", 1)],   [("batata_doce", 1.5)]]   # ~130
G_CARB_15   = [[("arroz_branco", 1.5)], [("arroz_integral", 1.5)], [("batata_doce", 2)]]     # ~186-195
G_CARB_2    = [[("arroz_branco", 2)],   [("arroz_integral", 2)],   [("batata_doce", 3)]]     # ~258-260
G_CARB_25   = [[("arroz_branco", 2.5)], [("arroz_integral", 2.5)], [("batata_doce", 3.5)]]   # ~310-325

# Almoço especial de domingo (churrasco). Substitui o almoço normal só no domingo.
CHURRASCO_ALMOCO = [("carne_bovina", 1.5), ("frango", 1), ("linguica", 1),
                    ("arroz_branco", 1), ("feijao", 1)]
FIX = lambda *itens: [list(itens)]   # slot de alternativa única (item fixo)

# Categorias de alimentos "intercambiáveis": evita dois do mesmo tipo na mesma
# refeição (ex.: pão integral + pão francês, ou arroz branco + arroz integral).
# Ao escolher a alternativa de um grupo, preferimos uma categoria ainda ausente.
_CATEGORIA = {
    "pao_frances": "pao", "pao_integral": "pao",
    "arroz_branco": "arroz", "arroz_integral": "arroz",
}

# Quantidade máxima de um mesmo alimento por refeição. Pão nunca passa de 2 por
# refeição (3+ é carboidrato demais e sem lógica).
_MAX_QTD_REFEICAO = {"pao_frances": 2, "pao_integral": 2}

# Refeição: (nome, horario, [slot, slot, ...]); slot = lista de alternativas.
# Horários neutros (não assumem treino de manhã) — o treino pode ser manhã,
# tarde ou noite, então a nutrição em volta dele é guiada por NOTA_TREINO.
MENUS = {
    # ── DESCANSO ─ menor carbo, déficit maior, proteína mantida (~1950 kcal) ──
    "descanso": [
        ("Café da manhã", "09:00", [FIX(("ovo", 3)), CAFE_CARB, FIX(("queijo_minas", 1)), LEITE]),
        ("Almoço", "13:00", [G_CARB_1, FIX(("feijao", 1)), PROT_ALMOCO, FIX(("azeite", 1))]),
        ("Lanche da tarde", "16:30", [FIX(("whey", 1)), FIX(("iogurte_grego", 1)), FIX(("pasta_amendoim", 1))]),
        ("Jantar", "20:00", [PROT_JANTAR, G_CARB_1, FIX(("azeite", 1))]),
    ],
    # ── RECUPERAÇÃO ─ leve, carbo um pouco maior que descanso (~2250 kcal) ──
    "recuperacao": [
        ("Café da manhã", "09:00", [FIX(("ovo", 2)), CAFE_CARB, FIX(("queijo_minas", 1)), LEITE, FIX(("banana", 1))]),
        ("Almoço", "13:00", [G_CARB_15, FIX(("feijao", 1)), PROT_ALMOCO, FIX(("azeite", 1))]),
        ("Lanche da tarde", "16:30", [FIX(("whey", 1)), FIX(("iogurte_grego", 1)), FIX(("banana", 1))]),
        ("Jantar", "20:00", [PROT_JANTAR, G_CARB_15, FIX(("azeite", 1))]),
    ],
    # ── Z2 LONGO ─ carbo alto para o pedal longo (~2900 kcal) ──
    "z2": [
        ("Café da manhã", "09:00", [FIX(("pao_frances", 2)), FIX(("ovo", 2)), FIX(("whey", 1)), LEITE, FIX(("banana", 2))]),
        ("Almoço", "13:00", [G_CARB_25, FIX(("feijao", 1)), PROT_ALMOCO, FIX(("azeite", 1)), FIX(("banana", 1))]),
        ("Lanche da tarde", "16:30", [FIX(("iogurte_grego", 1)), FIX(("aveia", 1)), FIX(("pasta_amendoim", 1)), FIX(("banana", 1))]),
        ("Jantar", "20:00", [PROT_JANTAR, G_CARB_25, FIX(("azeite", 1))]),
    ],
    # ── MODERADO (TEMPO / FORÇA) ─ carbo médio-alto (~2700 kcal) ──
    "moderado": [
        ("Café da manhã", "09:00", [CAFE_CARB, FIX(("ovo", 2)), FIX(("whey", 1)), LEITE, FIX(("banana", 1))]),
        ("Almoço", "13:00", [G_CARB_25, FIX(("feijao", 1)), PROT_ALMOCO, FIX(("azeite", 1)), FIX(("banana", 1))]),
        ("Lanche da tarde", "16:30", [FIX(("iogurte_grego", 1)), FIX(("whey", 1)), FIX(("pasta_amendoim", 1)), FIX(("banana", 1))]),
        ("Jantar", "20:00", [PROT_JANTAR, G_CARB_2, FIX(("azeite", 1))]),
    ],
    # ── INTENSO (TIROS / VO2MAX) ─ carbo alto p/ alta intensidade (~2900 kcal) ──
    "intenso": [
        ("Café da manhã", "09:00", [FIX(("pao_frances", 2)), FIX(("ovo", 2)), FIX(("whey", 1)), LEITE, FIX(("banana", 2))]),
        ("Almoço", "13:00", [G_CARB_25, FIX(("feijao", 1)), PROT_ALMOCO, FIX(("azeite", 1)), FIX(("banana", 1))]),
        ("Lanche da tarde", "16:30", [FIX(("iogurte_grego", 1)), FIX(("whey", 1)), FIX(("pasta_amendoim", 1)), FIX(("banana", 1))]),
        ("Jantar", "20:00", [PROT_JANTAR, G_CARB_25, FIX(("azeite", 1))]),
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
    "manha":    ("Café da manhã", "Almoço",          "Jantar"),
    "meio_dia": ("Café da manhã", "Almoço",          "Jantar"),
    "tarde":    ("Almoço",        "Lanche da tarde", "Café da manhã"),
    "noite":    ("Lanche da tarde", "Jantar",        "Café da manhã"),
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


def _merge_itens(itens: list[tuple]) -> list[tuple]:
    """Soma quantidades de itens repetidos (mesma chave), preservando a ordem da
    primeira aparição. Evita duplicação quando um item fixo coincide com o
    sorteado de um grupo (ex.: whey fixo + whey do lanche → 2 scoops) ou quando
    o ajuste de período adiciona um carbo já presente."""
    out: list[list] = []
    idx: dict = {}
    for chave, qtd in itens:
        if chave in idx:
            out[idx[chave]][1] += qtd
        else:
            idx[chave] = len(out)
            out.append([chave, qtd])
    return [(c, q) for c, q in out]


def _hhmm_para_time(hhmm: str):
    """Converte string 'HH:MM' em datetime.time. Levanta ValueError se inválido."""
    from datetime import time as dt_time
    h, m = hhmm.split(":")
    return dt_time(int(h), int(m))


def _reduzir_carbo(refeicoes_raw: list[dict], kcal_alvo: float) -> float:
    """Reduz porções de carboidrato (preservando proteína) para remover ~kcal_alvo
    do dia, começando pelas refeições mais tarde (jantar → café). Edita in place.
    Retorna o restante que NÃO conseguiu cortar (0.0 se cortou tudo)."""
    if kcal_alvo <= 0:
        return 0.0
    restante = kcal_alvo
    por_nome = {r["nome"]: r for r in refeicoes_raw}
    for nome in ("Jantar", "Lanche da tarde", "Almoço", "Café da manhã"):
        ref = por_nome.get(nome)
        if not ref or restante <= 0:
            continue
        novos = []
        for chave, qtd in ref["itens"]:
            if restante > 0 and chave in _CARBO_MOVEL and chave in ALIMENTOS:
                kcal_un = ALIMENTOS[chave]["kcal"]
                while qtd > 0 and restante > 0:
                    passo = 1 if qtd >= 1 else qtd
                    corte = kcal_un * passo
                    if corte > 2 * restante:   # cortar ultrapassaria demais o alvo
                        break
                    qtd = round(qtd - passo, 2)
                    restante -= corte
            if qtd > 0:
                novos.append((chave, qtd))
        ref["itens"] = novos
    return max(0.0, restante)


def _montar_refeicoes_raw(
    tipo, data_iso: str | None, horarios_cfg: dict | None, periodo: str | None
) -> tuple[list[dict], bool, dict]:
    """Monta as refeições 'cruas' (itens como (chave, qtd)) para um dia,
    aplicando a rotação de alternativas e opcionalmente o período do treino.

    Retorna (refeicoes_raw, aplicar_periodo, horarios).
    Helper extraído de plano_para_tipo para reutilização em capacidade_carbo_dia."""
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
        # categorias já garantidas pelos itens fixos (slots de 1 alternativa)
        cats = set()
        for slot in slots:
            if len(slot) == 1:
                cats |= {_CATEGORIA.get(ch) for ch, _ in slot[0]} - {None}

        escolhidos = []
        for slot in slots:
            base = (seed + pos) % len(slot)
            pos += 1
            alt = slot[base]
            if len(slot) > 1:
                # entre as alternativas (a partir da escolha do dia), prefere a
                # primeira que não repita uma categoria já presente na refeição.
                for k in range(len(slot)):
                    cand = slot[(base + k) % len(slot)]
                    cand_cats = {_CATEGORIA.get(ch) for ch, _ in cand} - {None}
                    if not (cand_cats & cats):
                        alt = cand
                        break
            cats |= {_CATEGORIA.get(ch) for ch, _ in alt} - {None}
            escolhidos.extend(alt)
        refeicoes_raw.append({
            "nome": nome, "horario": horarios.get(nome, horario_padrao),
            "itens": list(escolhidos), "observacao": None,
        })

    # 1b) domingo: churrasco no almoço (carne, frango, linguiça)
    if data_iso:
        try:
            if date.fromisoformat(data_iso).weekday() == 6:  # 6 = domingo
                for r in refeicoes_raw:
                    if r["nome"] == "Almoço":
                        r["itens"] = list(CHURRASCO_ALMOCO)
                        r["observacao"] = "🔥 Churrasco de domingo — aproveite! (volte ao plano na segunda)"
                        break
        except ValueError:
            pass

    # 2) com treino e período definido, redistribui o carbo em volta do treino
    aplicar = periodo in PERIODO_REFEICOES and tipo != TipoTreino.DESCANSO
    if aplicar:
        _aplicar_periodo(refeicoes_raw, periodo)

    return refeicoes_raw, aplicar, horarios


def capacidade_carbo_dia(
    tipo,
    data_iso: str | None,
    horarios_cfg: dict | None = None,
    periodo: str | None = None,
    apenas_apos=None,
) -> float:
    """Calcula quantas kcal de carboidrato móvel o dia tem disponível para corte.

    Se 'apenas_apos' (datetime.time) for fornecido, conta apenas refeições cujo
    horário configurado seja estritamente após esse instante — útil para calcular
    a capacidade restante a partir de um horário de registro da fuga.

    Retorna total em kcal (float)."""
    refeicoes_raw, _, _ = _montar_refeicoes_raw(tipo, data_iso, horarios_cfg, periodo)
    total = 0.0
    for r in refeicoes_raw:
        if apenas_apos is not None:
            try:
                hora_ref = _hhmm_para_time(r["horario"])
                if hora_ref <= apenas_apos:
                    continue  # refeição já passou (ou é agora) — não conta
            except (ValueError, AttributeError):
                pass  # horário inválido → inclui na conta por precaução
        for chave, qtd in r["itens"]:
            if chave in _CARBO_MOVEL and chave in ALIMENTOS:
                total += ALIMENTOS[chave]["kcal"] * qtd
    return total


def plano_para_tipo(tipo, data_iso: str | None = None, horarios_cfg: dict | None = None,
                    periodo: str | None = None, extras: list | None = None,
                    corte_kcal: float | None = None) -> dict:
    """Monta o cardápio do tipo de treino para uma data, com kcal/proteína por
    item, por refeição e total do dia.

    A cada dia escolhe uma combinação diferente de alternativas (variando pela
    data), mantendo as calorias-alvo. Sem data, usa um exemplo estável.
    Os horários das refeições vêm de horarios_cfg (config do usuário).

    Se 'periodo' for informado (manha/meio_dia/tarde/noite), redistribui o
    carboidrato em volta do treino (reforça o pré, marca o pós) sem mudar o tipo.

    corte_kcal: kcal de carboidrato a descontar do dia (débito de fuga, fixado
    no momento do registro). Quando None e há extras, usa a soma das kcal dos
    extras como alvo (retrocompatibilidade com docs sem corte_kcal salvo).
    Quando 0 explícito e não há extras, não corta nada.
    """
    if not isinstance(tipo, TipoTreino):
        try:
            tipo = TipoTreino(tipo)
        except ValueError:
            tipo = TipoTreino.DESCANSO

    # monta refeições cruas via helper reutilizável
    refeicoes_raw, aplicar, horarios = _montar_refeicoes_raw(tipo, data_iso, horarios_cfg, periodo)

    # 2b) corte de carbo: usa corte_kcal fixado (novo fluxo) ou soma extras (legado)
    # corte_kcal=None com extras = doc legado → fallback para somar kcal dos extras
    # corte_kcal=None sem extras = dia normal sem fuga
    # corte_kcal=0 explícito = sem corte neste dia (ex.: dia legado sem débito)
    if corte_kcal is not None:
        alvo_corte = corte_kcal
    else:
        alvo_corte = sum(int(e.get("kcal", 0)) for e in (extras or []))

    corte_aplicado = 0.0
    if alvo_corte > 0:
        nao_cortou = _reduzir_carbo(refeicoes_raw, alvo_corte)
        corte_aplicado = alvo_corte - nao_cortou

    # 3) expande os itens e soma kcal/proteína
    refeicoes = []
    kcal_total = 0
    prot_total = 0.0
    for r in refeicoes_raw:
        itens_norm = [
            (chave, min(qtd, _MAX_QTD_REFEICAO[chave]) if chave in _MAX_QTD_REFEICAO else qtd)
            for chave, qtd in _merge_itens(r["itens"])
        ]
        itens_exp = [_expandir_item(chave, qtd) for chave, qtd in itens_norm]
        r_kcal = sum(i["kcal"] for i in itens_exp)
        r_prot = round(sum(i["proteina_g"] for i in itens_exp), 1)
        kcal_total += r_kcal
        prot_total += r_prot
        refeicoes.append({
            "nome": r["nome"], "horario": r["horario"],
            "kcal": r_kcal, "proteina_g": r_prot, "itens": itens_exp,
            "observacao": r["observacao"],
        })

    # 3b) anexa os itens comidos fora do plano (já com o carbo do dia reduzido)
    if extras:
        itens_ex = [{
            "texto": e.get("resumo") or e.get("texto") or "Alimento fora do plano",
            "kcal": int(e.get("kcal", 0)),
            "proteina_g": round(float(e.get("proteina_g", 0)), 1),
        } for e in extras]
        ex_kcal = sum(i["kcal"] for i in itens_ex)
        ex_prot = round(sum(i["proteina_g"] for i in itens_ex), 1)
        refeicoes.append({
            "nome": "Fora do plano", "horario": "",
            "kcal": ex_kcal, "proteina_g": ex_prot, "itens": itens_ex,
            "observacao": "Você comeu isto fora do plano — o carboidrato do dia foi reduzido pra manter o total de calorias.",
        })
        kcal_total += ex_kcal
        prot_total += ex_prot

    # 3c) dia de débito herdado: corte_kcal > 0 mas sem extras (rollover de dia anterior)
    # Informa o usuário de forma discreta com um bloco informativo (sem somar kcal).
    elif corte_aplicado > 0:
        refeicoes.append({
            "nome": "Ajuste de carboidrato", "horario": "",
            "kcal": 0, "proteina_g": 0.0, "itens": [],
            "observacao": (
                f"Carboidrato reduzido (~{int(round(corte_aplicado))} kcal) "
                f"para compensar uma fuga registrada recentemente."
            ),
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
        # campo informativo: kcal efetivamente cortadas neste dia (0 se não houve corte)
        "corte_kcal": int(round(corte_aplicado)),
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
        # horário vazio = bloco especial (ex.: "Fora do plano", "Ajuste de carboidrato")
        prefixo = f"{r['horario']} · " if r.get("horario") else ""
        kcal_str = f" ({r['kcal']} kcal · {r['proteina_g']:g}g P)" if r["kcal"] > 0 or r["itens"] else ""
        linhas.append(f"*{prefixo}{r['nome']}*{kcal_str}")
        for i in r["itens"]:
            linhas.append(f"  • {i['texto']}")
        if r.get("observacao"):
            linhas.append(f"  {r['observacao']}")
        linhas.append("")

    linhas.append("💧 Mínimo 3L de água/dia")
    linhas.append("_MTB Nutrition Bot 🤖_")
    return "\n".join(linhas)


def formatar_refeicao_whatsapp(data_iso: str, plano: dict, nome_refeicao: str) -> str | None:
    """Monta a mensagem de UMA refeição específica do dia (ex.: só o jantar).
    Retorna None se a refeição não existir no plano do dia."""
    from datetime import datetime
    ref = next((r for r in plano["refeicoes"]
                if r["nome"].lower() == nome_refeicao.lower()), None)
    if not ref:
        return None
    d = datetime.strptime(data_iso, "%Y-%m-%d")
    dias = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    linhas = [
        f"🍽️ *{ref['nome']} — {dias[d.weekday()]}, {d.strftime('%d/%m')}*",
        f"⏰ {ref['horario']} · {ref['kcal']} kcal · {ref['proteina_g']:g}g proteína",
        "",
    ]
    for i in ref["itens"]:
        linhas.append(f"  • {i['texto']}")
    if ref.get("observacao"):
        linhas += ["", ref["observacao"]]
    linhas += ["", "_MTB Nutrition Bot 🤖_"]
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
