import anthropic
from datetime import datetime, timezone, timedelta

from config.settings import settings
from app.services.mongo_service import get_db

_client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
_MODEL = "claude-sonnet-4-6"
_MAX_MENSAGENS_DB = 100
_MAX_HISTORICO_IA = 20

_TOOLS = [
    {
        "name": "ver_semana",
        "description": (
            "Busca os treinos planejados para uma semana específica do calendário do atleta. "
            "Use antes de fazer qualquer alteração para ver o que já está agendado."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "semana_inicio": {
                    "type": "string",
                    "description": "Segunda-feira da semana, formato YYYY-MM-DD.",
                }
            },
            "required": ["semana_inicio"],
        },
    },
    {
        "name": "adicionar_treino",
        "description": (
            "Adiciona ou substitui um treino em um dia específico do calendário. "
            "Tipos disponíveis: Z2_LONGO (pedal longo Z2), TIROS (séries de alta intensidade), "
            "VO2MAX (esforços VO2max), TEMPO (limiar), FORCA (academia/musculação/força), "
            "RECUPERACAO (pedalada leve), DESCANSO (sem treino). "
            "Use FORCA para qualquer treino de academia, musculação ou força."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "data": {
                    "type": "string",
                    "description": "Data do treino, formato YYYY-MM-DD.",
                },
                "tipo": {
                    "type": "string",
                    "enum": ["Z2_LONGO", "TIROS", "VO2MAX", "TEMPO", "FORCA", "RECUPERACAO", "DESCANSO"],
                    "description": "Tipo do treino.",
                },
                "duracao_min": {
                    "type": "integer",
                    "description": "Duração em minutos.",
                },
                "descricao": {
                    "type": "string",
                    "description": "Descrição detalhada (exercícios, séries, intensidade, observações).",
                },
            },
            "required": ["data", "tipo", "duracao_min", "descricao"],
        },
    },
    {
        "name": "remover_treino",
        "description": "Remove o treino de um dia (transforma em descanso).",
        "input_schema": {
            "type": "object",
            "properties": {
                "data": {
                    "type": "string",
                    "description": "Data do treino a remover, formato YYYY-MM-DD.",
                }
            },
            "required": ["data"],
        },
    },
    {
        "name": "mover_treino",
        "description": "Move um treino de um dia para outro, ou troca dois dias entre si.",
        "input_schema": {
            "type": "object",
            "properties": {
                "origem": {
                    "type": "string",
                    "description": "Data de origem, formato YYYY-MM-DD.",
                },
                "destino": {
                    "type": "string",
                    "description": "Data de destino, formato YYYY-MM-DD.",
                },
                "modo": {
                    "type": "string",
                    "enum": ["sobrescrever", "swap"],
                    "description": (
                        "sobrescrever: move para o destino (origem vira descanso). "
                        "swap: troca os conteúdos dos dois dias."
                    ),
                },
            },
            "required": ["origem", "destino", "modo"],
        },
    },
]


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

    linhas = [
        "Você é o assistente pessoal de treino e nutrição de um ciclista de MTB.",
        "Responda sempre em português do Brasil, com tom amigável e direto.",
        "Você pode discutir treinos, nutrição, ajustes de duração/intensidade, periodização e dúvidas gerais.",
        "Você tem ferramentas para ler e modificar o calendário de treinos diretamente.",
        "Quando o atleta pedir para adicionar, remover ou alterar treinos, use as ferramentas — não apenas sugira.",
        "Antes de propor alterações, consulte a semana com ver_semana para saber o que já está agendado.",
        "Após cada ação, confirme o que foi feito e explique brevemente a escolha.",
    ]

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

    try:
        from app.services.config_service import get_zonas
        zc = await get_zonas(user_id)
        zs = zc.get("zonas") or []
        if zs:
            zonas_txt = " | ".join(f"Z{z['zona']} {z['min']}-{z['max']}bpm" for z in zs)
            linhas.append(f"Zonas de FC: {zonas_txt}")
    except Exception:
        pass

    try:
        from app.services.treino_semana_service import get_treinos_semana

        hoje_str = datetime.now().date().isoformat()
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


async def _executar_ferramenta(user_id: str, nome: str, args: dict) -> str:
    from app.services.treino_semana_service import (
        get_treinos_semana,
        criar_treino_dia,
        remover_treino_dia,
        mover_treino,
    )
    try:
        if nome == "ver_semana":
            treinos = await get_treinos_semana(user_id, args["semana_inicio"])
            if not treinos:
                return f"Nenhum treino encontrado para a semana de {args['semana_inicio']}."
            linhas = []
            for t in sorted(treinos, key=lambda x: x.get("data", "")):
                tipo = t.get("tipo", "DESCANSO")
                data = t.get("data", "")
                dur = t.get("duracao_min")
                desc = (t.get("descricao") or "")[:120]
                resultado = t.get("resultado")
                if resultado and resultado.get("duracao_min"):
                    linha = f"{data}: [{tipo}] REALIZADO {resultado['duracao_min']}min"
                elif tipo != "DESCANSO":
                    linha = f"{data}: [{tipo}] {dur}min — {desc}"
                else:
                    linha = f"{data}: DESCANSO"
                linhas.append(linha)
            return "\n".join(linhas)

        elif nome == "adicionar_treino":
            await criar_treino_dia(
                user_id,
                args["data"],
                args["tipo"],
                args.get("duracao_min", 60),
                args.get("descricao"),
            )
            return f"Treino adicionado: {args['data']} [{args['tipo']}] {args.get('duracao_min', 60)}min"

        elif nome == "remover_treino":
            resultado = await remover_treino_dia(user_id, args["data"])
            return f"Treino de {args['data']} removido (era {resultado['tipo_antigo']})."

        elif nome == "mover_treino":
            await mover_treino(
                user_id, args["origem"], args["destino"], args.get("modo", "sobrescrever")
            )
            return f"Treino movido de {args['origem']} para {args['destino']} (modo: {args.get('modo', 'sobrescrever')})."

        else:
            return f"Ferramenta '{nome}' não reconhecida."

    except ValueError as exc:
        return f"Erro: {exc}"
    except Exception as exc:
        return f"Erro inesperado: {exc}"


def _content_to_api(content) -> list[dict]:
    """Converte blocos do SDK para dicts aceitos pela API na próxima chamada."""
    result = []
    for block in content:
        if block.type == "text":
            result.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            result.append({
                "type": "tool_use",
                "id": block.id,
                "name": block.name,
                "input": block.input,
            })
    return result


async def responder(user_id: str, mensagem: str) -> str:
    historico = await get_historico(user_id)
    sistema = await _build_sistema(user_id)

    messages = [
        {"role": m["role"], "content": m["texto"]}
        for m in historico
    ]
    messages.append({"role": "user", "content": mensagem})

    resposta = None
    for _ in range(8):
        try:
            resp = await _client.messages.create(
                model=_MODEL,
                max_tokens=2000,
                system=sistema,
                messages=messages,
                tools=_TOOLS,
            )
        except Exception:
            resposta = "Não consegui processar sua mensagem agora. Tente novamente em instantes."
            break

        if resp.stop_reason == "tool_use":
            assistant_content = _content_to_api(resp.content)
            messages.append({"role": "assistant", "content": assistant_content})

            tool_results = []
            for block in resp.content:
                if block.type == "tool_use":
                    resultado = await _executar_ferramenta(user_id, block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": resultado,
                    })
            messages.append({"role": "user", "content": tool_results})

        else:
            for block in resp.content:
                if hasattr(block, "text"):
                    resposta = block.text.strip()
                    break
            if not resposta:
                resposta = "Não consegui gerar uma resposta."
            break

    if resposta is None:
        resposta = "Não consegui completar a operação. Tente novamente."

    await _salvar_mensagem(user_id, "user", mensagem)
    await _salvar_mensagem(user_id, "assistant", resposta)
    return resposta
