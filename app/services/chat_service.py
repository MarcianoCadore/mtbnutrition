import anthropic
from datetime import datetime, timezone, timedelta

from config.settings import settings
from app.services.mongo_service import get_db

_client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
_MODEL = "claude-sonnet-4-6"
_MAX_MENSAGENS_DB = 100   # máx mensagens salvas por usuário
_MAX_HISTORICO_IA = 20    # últimas N mensagens enviadas ao modelo


async def get_historico(user_id: str, limite: int = _MAX_HISTORICO_IA) -> list[dict]:
    db = get_db()
    doc = await db.chat_historico.find_one({"user_id": user_id})
    if not doc:
        return []
    return doc.get("mensagens", [])[-limite:]


async def _salvar_mensagem(user_id: str, role: str, texto: str) -> None:
    db = get_db()
    msg = {"role": role, "texto": texto, "ts": datetime.now(timezone.utc).isoformat()}
    await db.chat_historico.update_one(
        {"user_id": user_id},
        {
            "$push": {"mensagens": {"$each": [msg], "$slice": -_MAX_MENSAGENS_DB}},
            "$set": {"atualizado_em": datetime.now(timezone.utc)},
        },
        upsert=True,
    )


async def _build_sistema(user_id: str) -> str:
    from app.services.user_service import get_por_id
    from app.services.treino_semana_service import get_treinos_semana

    linhas = [
        "Você é o assistente pessoal de treino e nutrição de um ciclista de MTB.",
        "Responda sempre em português do Brasil, com tom amigável e direto.",
        "Você pode discutir treinos, nutrição, ajustes de duração/intensidade, periodização e dúvidas gerais.",
        "Quando sugerir ajustes em treinos, explique o motivo e os benefícios, mas lembre que o atleta deve confirmar pela interface do app.",
    ]

    # Perfil do atleta
    try:
        u = await get_por_id(user_id)
        if u:
            nome = u.get("nome") or "Atleta"
            perfil = u.get("perfil") or {}
            prefs = u.get("preferencias") or {}

            _OBJ = {
                "performance_mtb": "melhorar performance MTB (modelo polarizado)",
                "aumentar_potencia": "aumentar potência e FTP",
                "base_aerobica": "construir base aeróbica (volume Z2)",
                "manter_performance": "manter a performance atual",
                "emagrecimento": "emagrecer mantendo massa muscular e potência",
            }
            obj = _OBJ.get(prefs.get("objetivo") or "performance_mtb", "performance MTB")

            linhas.append(f"\n== ATLETA ==")
            linhas.append(f"Nome: {nome}")
            if perfil.get("idade"):
                linhas.append(f"Idade: {perfil['idade']} anos")
            if perfil.get("peso_kg"):
                linhas.append(f"Peso: {perfil['peso_kg']} kg")
            if perfil.get("altura_cm"):
                linhas.append(f"Altura: {perfil['altura_cm']} cm")
            if perfil.get("fc_max"):
                linhas.append(f"FC máxima: {perfil['fc_max']} bpm")
            linhas.append(f"Objetivo: {obj}")
    except Exception:
        pass

    # Zonas de FC
    try:
        from app.services.config_service import get_zonas
        zc = await get_zonas(user_id)
        zs = zc.get("zonas") or []
        if zs:
            zonas_txt = " | ".join(f"Z{z['zona']} {z['min']}-{z['max']}bpm" for z in zs)
            linhas.append(f"Zonas de FC: {zonas_txt}")
    except Exception:
        pass

    # Semana anterior, atual e próxima
    try:
        from app.services.treino_semana_service import get_treinos_semana

        hoje_str = datetime.now().date().isoformat()
        # calcula segunda-feira da semana atual
        hoje_dt = datetime.now().date()
        seg_atual = hoje_dt - timedelta(days=hoje_dt.weekday())

        linhas.append(f"\n== TREINOS (semana anterior, atual, próxima) ==")
        linhas.append(f"Hoje: {hoje_str}")

        for delta_sem in [-1, 0, 1]:
            seg = (seg_atual + timedelta(weeks=delta_sem)).isoformat()
            treinos = await get_treinos_semana(user_id, seg)
            if not treinos:
                continue
            label = {-1: "Semana passada", 0: "Semana atual", 1: "Próxima semana"}[delta_sem]
            linhas.append(f"\n{label} (início {seg}):")
            for t in treinos:
                data = t.get("data") or ""
                tipo = t.get("tipo") or "DESCANSO"
                dur = t.get("duracao_min")
                dist = t.get("distancia_km")
                desc = (t.get("descricao") or "")[:80]
                resultado = t.get("resultado")

                if resultado and resultado.get("duracao_min"):
                    r_dur = resultado["duracao_min"]
                    r_dist = resultado.get("distancia_km")
                    nota = (resultado.get("analise_ia") or {}).get("nota")
                    linha = f"  {data} [{tipo}] REALIZADO {r_dur}min"
                    if r_dist:
                        linha += f" {r_dist}km"
                    if nota is not None:
                        linha += f" (nota {nota})"
                else:
                    linha = f"  {data} [{tipo}] PLANEJADO"
                    if dur:
                        linha += f" {dur}min"
                    if dist:
                        linha += f" {dist}km"
                if desc:
                    linha += f" — {desc}"
                linhas.append(linha)
    except Exception:
        pass

    return "\n".join(linhas)


async def responder(user_id: str, mensagem: str) -> str:
    historico = await get_historico(user_id)
    sistema = await _build_sistema(user_id)

    messages = [
        {"role": m["role"], "content": m["texto"]}
        for m in historico
    ]
    messages.append({"role": "user", "content": mensagem})

    try:
        resp = await _client.messages.create(
            model=_MODEL,
            max_tokens=1000,
            system=sistema,
            messages=messages,
        )
        resposta = resp.content[0].text.strip()
    except Exception:
        resposta = "Não consegui processar sua mensagem agora. Tente novamente em instantes."

    await _salvar_mensagem(user_id, "user", mensagem)
    await _salvar_mensagem(user_id, "assistant", resposta)
    return resposta
