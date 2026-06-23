"""Configurações por usuário: horários de refeição e zonas de FC, armazenados no
doc do usuário em db.users (campos 'horarios' e 'zonas').

Ajustes de fuga do plano (coleção db.ajustes_dia) são escopados por user_id
usando o filtro {"user_id": user_id, "data": data}.
"""
import re

from app.services.mongo_service import get_db
from app.services.nutricao_service import DEFAULT_HORARIOS

_RE_HORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

DEFAULT_FTP = 200  # watts — substituído pelo valor real do usuário

# 7 zonas de potência baseadas no modelo Coggan (% do FTP)
_ZONAS_POT_PCT = [
    (1, 0.00, 0.55, "Recuperação ativa"),
    (2, 0.56, 0.75, "Resistência"),
    (3, 0.76, 0.90, "Tempo/Ritmo"),
    (4, 0.91, 1.05, "Limiar"),
    (5, 1.06, 1.20, "VO₂Máx"),
    (6, 1.21, 1.50, "Anaeróbico"),
    (7, 1.51, 9.99, "Neuromuscular"),
]


def calc_zonas_potencia(ftp: int) -> list[dict]:
    """Calcula as 7 zonas de potência (watts) a partir do FTP."""
    zonas = []
    for zona, pct_min, pct_max, nome in _ZONAS_POT_PCT:
        min_w = round(ftp * pct_min) if pct_min > 0 else 0
        max_w = round(ftp * pct_max) if pct_max < 9 else 9999
        zonas.append({"zona": zona, "min": min_w, "max": max_w, "nome": nome})
    return zonas


# Zonas de FC padrão calibradas com FC máx 185 e LTHR 165 (89% de 185).
DEFAULT_ZONAS = {
    "fc_max": 185,
    "limiar": 165,
    "zonas": [
        {"zona": 1, "min": 120, "max": 141},
        {"zona": 2, "min": 142, "max": 154},
        {"zona": 3, "min": 155, "max": 161},
        {"zona": 4, "min": 162, "max": 172},
        {"zona": 5, "min": 173, "max": 185},
    ],
}

# Ordem natural das refeições no dia (chave -> rótulo amigável).
ORDEM_REFEICOES = [
    ("cafe", "Café da manhã"),
    ("lanche_manha", "Lanche da manhã"),
    ("almoco", "Almoço"),
    ("lanche_tarde", "Lanche da tarde"),
    ("jantar", "Jantar"),
]


def _para_min(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _validar_ordem(cfg: dict) -> None:
    """Garante café < almoço < lanche < jantar (pega confusão de manhã/noite,
    ex.: jantar marcado às 09:00 em vez de 21:00)."""
    prev_min = prev_nome = prev_hora = None
    for chave, nome in ORDEM_REFEICOES:
        atual = _para_min(cfg[chave])
        if prev_min is not None and atual <= prev_min:
            raise ValueError(
                f"{nome} ({cfg[chave]}) precisa ser depois de {prev_nome} ({prev_hora}). "
                f"Confira se não trocou manhã por noite (ex.: 09:00 em vez de 21:00)."
            )
        prev_min, prev_nome, prev_hora = atual, nome, cfg[chave]


# ── Horários das refeições (por usuário) ─────────────────────────────────────

async def get_horarios(user_id: str) -> dict:
    """Horários das refeições do usuário (ou os padrões se não configurado)."""
    from app.services.user_service import get_por_id
    user = await get_por_id(user_id)
    if user and user.get("horarios"):
        return {**DEFAULT_HORARIOS, **user["horarios"]}
    return dict(DEFAULT_HORARIOS)


async def salvar_horarios(user_id: str, cfg: dict) -> dict:
    """Valida e salva os horários (HH:MM) no doc do usuário. Ignora chaves desconhecidas."""
    from app.services.user_service import atualizar_usuario
    limpo = {}
    for k in DEFAULT_HORARIOS:
        v = (cfg.get(k) or "").strip()
        if v and not _RE_HORA.match(v):
            raise ValueError(f"Horário inválido para '{k}': {v} (use HH:MM)")
        if v:
            limpo[k] = v
    # valida a ordem do dia já com os defaults aplicados (campos não enviados)
    _validar_ordem({**DEFAULT_HORARIOS, **limpo})
    horarios_completos = {**DEFAULT_HORARIOS, **limpo}
    await atualizar_usuario(user_id, {"horarios": horarios_completos})
    return horarios_completos


# ── Zonas de frequência cardíaca (por usuário) ────────────────────────────────

async def get_zonas(user_id: str) -> dict:
    """Zonas de FC do usuário (ou os padrões se não configurado)."""
    from app.services.user_service import get_por_id
    user = await get_por_id(user_id)
    if user and user.get("zonas"):
        return user["zonas"]
    return {k: v for k, v in DEFAULT_ZONAS.items()}


def _validar_zonas(data: dict) -> dict:
    """Valida e normaliza as 5 zonas + fc_max/limiar. Levanta ValueError."""
    zonas_in = data.get("zonas") or []
    if len(zonas_in) != 5:
        raise ValueError("São necessárias exatamente 5 zonas (Z1 a Z5).")

    zonas = []
    prev_max = None
    for i, z in enumerate(sorted(zonas_in, key=lambda x: int(x.get("zona", 0))), start=1):
        try:
            mn = int(z["min"])
            mx = int(z["max"])
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"Zona {i}: informe min e max em bpm (números inteiros).")
        if not (60 <= mn < mx <= 230):
            raise ValueError(f"Zona {i}: faixa inválida ({mn}-{mx}). Use 60–230 bpm com min < max.")
        if prev_max is not None:
            if mn < prev_max:
                raise ValueError(f"Zona {i} ({mn}) deve começar a partir do fim da zona anterior ({prev_max}).")
            if mn > prev_max + 1:
                mn = prev_max + 1  # preenche gap: garante zonas contínuas sem bpm órfão
        prev_max = mx
        zonas.append({"zona": i, "min": mn, "max": mx})

    fc_max = data.get("fc_max")
    limiar = data.get("limiar")
    try:
        fc_max = int(fc_max) if fc_max not in (None, "") else zonas[-1]["max"]
        limiar = int(limiar) if limiar not in (None, "") else None
    except (TypeError, ValueError):
        raise ValueError("FC máxima e limiar devem ser números inteiros.")

    metodo = str(data.get("metodo") or "fcmax")
    if metodo not in ("fcmax", "ll"):
        metodo = "fcmax"
    return {"fc_max": fc_max, "limiar": limiar, "metodo": metodo, "zonas": zonas}


async def salvar_zonas(user_id: str, data: dict) -> dict:
    """Valida e persiste as zonas de FC no doc do usuário."""
    from app.services.user_service import atualizar_usuario
    limpo = _validar_zonas(data)
    await atualizar_usuario(user_id, {"zonas": limpo})
    return limpo


async def zonas_bpm_map(user_id: str) -> dict:
    """Mapa {numero_da_zona: {'min': bpm, 'max': bpm}} para montar os workouts."""
    cfg = await get_zonas(user_id)
    return {int(z["zona"]): {"min": int(z["min"]), "max": int(z["max"])} for z in cfg["zonas"]}


# ── FTP e zonas de potência (por usuário) ────────────────────────────────────

async def get_ftp(user_id: str) -> tuple[int | None, str]:
    """FTP (watts) e modo de uso de potência. Retorna (None, 'indoor') se não configurado."""
    from app.services.user_service import get_por_id
    user = await get_por_id(user_id) or {}
    ftp = int(user.get("ftp") or 0) or None
    modo = user.get("potencia_modo") or "indoor"
    return ftp, modo


async def salvar_ftp(user_id: str, ftp: int, modo: str = "indoor") -> dict:
    """Salva o FTP e o modo de uso de potência. Retorna as zonas calculadas.

    modo:
      "indoor"  — alvos de watts só em VO2MAX/TIROS/TEMPO/FORCA (feitos no rolo)
      "sempre"  — todos os workouts com watts (medidor na bike de rua/MTB também)
      "nunca"   — FTP salvo só para análise; workouts usam apenas FC
    """
    from app.services.user_service import atualizar_usuario
    from datetime import date
    if not (50 <= ftp <= 700):
        raise ValueError(f"FTP inválido: {ftp}W. Use um valor entre 50 e 700W.")
    if modo not in ("indoor", "sempre", "nunca"):
        modo = "indoor"
    await atualizar_usuario(user_id, {
        "ftp": ftp,
        "potencia_modo": modo,
        "ultimo_teste_ftp": date.today().isoformat(),
    })
    return {"ftp": ftp, "potencia_modo": modo, "zonas": calc_zonas_potencia(ftp)}


async def dias_desde_ultimo_ftp(user_id: str) -> int | None:
    """Retorna quantos dias se passaram desde o último teste de FTP.

    Lê `ultimo_teste_ftp` do documento do usuário. Se nunca testou, retorna None.
    Também inspeciona as semanas registradas buscando TESTE_FTP concluído.
    """
    from app.services.user_service import get_por_id
    from app.services.mongo_service import get_db
    from datetime import date

    user = await get_por_id(user_id) or {}
    data_str = user.get("ultimo_teste_ftp")

    # Fallback: procura TESTE_FTP mais recente nas semanas registradas
    if not data_str:
        db = get_db()
        doc = await db.semanas.find_one(
            {"user_id": user_id, "treinos.tipo": "TESTE_FTP"},
            sort=[("semana_inicio", -1)],
        )
        if doc:
            datas_ftp = [
                t["data"] for t in doc.get("treinos", [])
                if t.get("tipo") == "TESTE_FTP" and t.get("data")
            ]
            if datas_ftp:
                data_str = max(datas_ftp)

    if not data_str:
        return None
    try:
        ultimo = date.fromisoformat(data_str)
        return (date.today() - ultimo).days
    except ValueError:
        return None


async def get_zonas_potencia(user_id: str) -> dict | None:
    """FTP + modo + 7 zonas de potência. Retorna None se FTP não configurado."""
    ftp, modo = await get_ftp(user_id)
    if not ftp:
        return None
    return {"ftp": ftp, "potencia_modo": modo, "zonas": calc_zonas_potencia(ftp)}


async def zonas_watts_map(user_id: str) -> dict | None:
    """Mapa {zona: {'min': w, 'max': w, 'nome': str}} para workouts Garmin. None se FTP não configurado."""
    zp = await get_zonas_potencia(user_id)
    if not zp:
        return None
    return {z["zona"]: {"min": z["min"], "max": z["max"], "nome": z["nome"]} for z in zp["zonas"]}


# ── Ajustes de "fuga" do plano (o que comi fora, por dia) ─────────────────────
# A partir da Fase 1 multiusuário, escopados por {"user_id": user_id, "data": data}.

async def extras_do_dia(user_id: str, data: str) -> list:
    """Lista de itens comidos fora do plano numa data (ISO YYYY-MM-DD)."""
    db = get_db()
    doc = await db.ajustes_dia.find_one({"user_id": user_id, "data": data})
    return (doc or {}).get("extras", [])


async def adicionar_extra_dia(user_id: str, data: str, extra: dict) -> list:
    """Acrescenta um item comido fora do plano ao dia. Retorna a lista atualizada."""
    item = {
        "resumo": str(extra.get("resumo", "")).strip() or "Alimento fora do plano",
        "kcal": max(0, int(extra.get("kcal", 0))),
        "proteina_g": round(float(extra.get("proteina_g", 0)), 1),
    }
    db = get_db()
    await db.ajustes_dia.update_one(
        {"user_id": user_id, "data": data},
        {"$push": {"extras": item}, "$set": {"user_id": user_id, "data": data}},
        upsert=True,
    )
    return await extras_do_dia(user_id, data)


async def remover_ajuste_dia(user_id: str, data: str) -> None:
    """Remove todos os ajustes (extras) de um dia — volta ao plano original."""
    db = get_db()
    await db.ajustes_dia.delete_one({"user_id": user_id, "data": data})


async def adicionar_corte_dia(user_id: str, data: str, kcal: float) -> None:
    """Acumula kcal de corte de carboidrato no dia (débito de fuga).
    Usa $inc para somar ao valor existente (múltiplas fugas acumulam corretamente)."""
    db = get_db()
    await db.ajustes_dia.update_one(
        {"user_id": user_id, "data": data},
        {"$inc": {"corte_kcal": int(round(kcal))}, "$set": {"user_id": user_id, "data": data}},
        upsert=True,
    )


async def corte_do_dia(user_id: str, data: str) -> int | None:
    """Retorna o corte de kcal de carboidrato registrado para o dia.

    Semântica especial para retrocompatibilidade com docs legados:
    - Doc sem 'corte_kcal' MAS com 'extras' → retorna None (sinaliza: use o
      fallback de somar extras em plano_para_tipo).
    - Doc com 'corte_kcal' explícito → retorna o valor (pode ser 0).
    - Sem doc → retorna None (idem: fallback de extras).
    """
    db = get_db()
    doc = await db.ajustes_dia.find_one({"user_id": user_id, "data": data})
    if doc is None:
        return None
    if "corte_kcal" not in doc:
        # doc legado: tem extras mas não tem corte_kcal — sinaliza para o caller
        # usar o fallback de somar as kcal dos extras em plano_para_tipo.
        return None
    return int(doc["corte_kcal"])


async def ajuste_do_dia(user_id: str, data: str) -> dict:
    """Lê extras e corte_kcal numa única consulta ao banco.
    Útil para callers que precisam dos dois campos (reduz round-trips)."""
    db = get_db()
    doc = await db.ajustes_dia.find_one({"user_id": user_id, "data": data}) or {}
    corte = doc.get("corte_kcal")
    return {
        "extras": doc.get("extras", []),
        # None = sem corte explícito (doc legado ou inexistente) → usar fallback
        "corte_kcal": int(corte) if corte is not None else None,
    }


# ── Overrides pessoais do cardápio (ajuste permanente via chat) ──────────────
# Coleção db.overrides_cardapio, escopada por user_id. Cada doc fixa a
# quantidade (em porções) de um alimento ou categoria, opcionalmente só numa
# refeição específica — substitui a quantidade que o cardápio fixo escolheria.

async def overrides_cardapio(user_id: str) -> list:
    """Lista os overrides de cardápio ativos do usuário."""
    db = get_db()
    cursor = db.overrides_cardapio.find({"user_id": user_id}, {"_id": 0})
    return [doc async for doc in cursor]


async def definir_override_cardapio(
    user_id: str, escopo: str, chave: str, porcoes: float, refeicao: str | None = None
) -> dict:
    """Cria ou atualiza (upsert) o override de quantidade de um alimento/categoria
    para o usuário. Retorna o doc salvo."""
    from datetime import datetime, timezone

    agora = datetime.now(timezone.utc)
    filtro = {"user_id": user_id, "escopo": escopo, "chave": chave, "refeicao": refeicao}
    db = get_db()
    await db.overrides_cardapio.update_one(
        filtro,
        {
            "$set": {**filtro, "porcoes": float(porcoes), "origem": "chat", "atualizado_em": agora},
            "$setOnInsert": {"criado_em": agora},
        },
        upsert=True,
    )
    return await db.overrides_cardapio.find_one(filtro, {"_id": 0})


async def remover_override_cardapio(
    user_id: str, escopo: str, chave: str, refeicao: str | None = None
) -> None:
    """Remove um override de cardápio do usuário — volta ao valor padrão do menu fixo."""
    db = get_db()
    await db.overrides_cardapio.delete_one(
        {"user_id": user_id, "escopo": escopo, "chave": chave, "refeicao": refeicao}
    )


# ── Histórico do chat de ajuste do cardápio ──────────────────────────────────
# Um doc por usuário em db.chat_nutricao, com a lista de mensagens (mantém só
# as últimas _MAX_MENSAGENS_CHAT pra não crescer sem limite nem inflar o
# prompt da IA).

_MAX_MENSAGENS_CHAT = 30


async def historico_chat_nutricao(user_id: str) -> list:
    """Mensagens da conversa de ajuste do cardápio do usuário (mais antiga primeiro)."""
    db = get_db()
    doc = await db.chat_nutricao.find_one({"user_id": user_id})
    return (doc or {}).get("mensagens", [])


async def adicionar_mensagem_chat(user_id: str, role: str, texto: str) -> list:
    """Acrescenta uma mensagem ao histórico (role: 'user' ou 'assistente') e
    devolve o histórico atualizado, já truncado nas últimas _MAX_MENSAGENS_CHAT."""
    from datetime import datetime, timezone

    msg = {"role": role, "texto": texto, "criado_em": datetime.now(timezone.utc)}
    db = get_db()
    await db.chat_nutricao.update_one(
        {"user_id": user_id},
        {"$push": {"mensagens": msg}, "$set": {"user_id": user_id}},
        upsert=True,
    )
    historico = await historico_chat_nutricao(user_id)
    if len(historico) > _MAX_MENSAGENS_CHAT:
        historico = historico[-_MAX_MENSAGENS_CHAT:]
        await db.chat_nutricao.update_one(
            {"user_id": user_id}, {"$set": {"mensagens": historico}}
        )
    return historico


async def limpar_chat_nutricao(user_id: str) -> None:
    """Apaga o histórico da conversa de ajuste do cardápio do usuário."""
    db = get_db()
    await db.chat_nutricao.delete_one({"user_id": user_id})
