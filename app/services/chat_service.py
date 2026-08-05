import anthropic
import logging
from datetime import datetime, timezone, timedelta

import pytz

from config.settings import settings
from app.services import custo_ia_service
from app.services.mongo_service import get_db

logger = logging.getLogger(__name__)

_client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
_MODEL = "claude-sonnet-4-6"
_MAX_MENSAGENS_DB = 100
_MAX_HISTORICO_IA = 20
_TZ = pytz.timezone("America/Sao_Paulo")

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
            "VO2MAX (esforços VO2max), TEMPO (limiar), "
            "FORCA (força específica NA BIKE — cadência baixa, marcha pesada), "
            "ACADEMIA (musculação no ginásio — agachamento, supino, remada, etc.), "
            "RECUPERACAO (pedalada leve), DESCANSO (sem treino). "
            "Use FORCA para treino de força na bike. Use ACADEMIA para musculação no ginásio."
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
                    "enum": ["Z2_LONGO", "TIROS", "VO2MAX", "TEMPO", "FORCA", "ACADEMIA", "RECUPERACAO", "DESCANSO"],
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
    {
        "name": "reavaliar_treino",
        "description": (
            "Refaz a avaliação de um treino JÁ REALIZADO (nota, pontos fortes/fracos e TSS). "
            "USE SEMPRE que o atleta disser que os dados de frequência cardíaca daquele treino "
            "não valem: cinta cardíaca sem bateria, bateria fraca, cinta descarregada, cinta "
            "solta/mal posicionada, esqueceu a cinta, não usou cinta, FC travada, FC absurda ou "
            "'ignora a FC desse treino'. Com ignorar_fc=true a nova avaliação descarta FC, tempo "
            "em zonas de FC e o TSS calculado por FC, julgando por potência, volume, distância e "
            "cadência — e não penaliza a nota pela falta de FC. Use ignorar_fc=false para desfazer "
            "e voltar a considerar a FC."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "data": {
                    "type": "string",
                    "description": "Data do treino a reavaliar, formato YYYY-MM-DD.",
                },
                "ignorar_fc": {
                    "type": "boolean",
                    "description": "true (padrão) descarta a FC da avaliação; false volta a considerá-la.",
                },
                "motivo": {
                    "type": "string",
                    "description": "Motivo curto, nas palavras do atleta (ex.: 'cinta sem bateria').",
                },
            },
            "required": ["data"],
        },
    },
    {
        "name": "registrar_treino_realizado",
        "description": (
            "Marca um treino do calendário como REALIZADO a partir do relato do atleta. "
            "USE SEMPRE que ele disser que fez, completou ou terminou um treino que não "
            "chegou pelo Garmin/Strava: academia, pedal sem relógio, rolo sem sensor, ou "
            "quando ele disser que não consegue registrar no sistema. "
            "NUNCA use adicionar_treino para registrar sessão feita — adicionar_treino "
            "reescreve o PLANO do dia, apaga a prescrição e não marca nada como realizado. "
            "Esta ferramenta preserva o treino planejado e gera nota e análise da sessão. "
            "Recusa se o treino já veio do dispositivo: dado medido tem prioridade."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "data": {
                    "type": "string",
                    "description": "Data do treino realizado, formato YYYY-MM-DD.",
                },
                "duracao_min": {
                    "type": "integer",
                    "description": (
                        "Duração real em minutos. Se o atleta não disser, omita — "
                        "a duração do planejado é usada."
                    ),
                },
                "relato": {
                    "type": "string",
                    "description": (
                        "O que o atleta contou, nas palavras dele: exercícios ou séries "
                        "executados, cargas, sensações, o que não conseguiu fazer."
                    ),
                },
                "distancia_km": {
                    "type": "number",
                    "description": "Distância em km, se ele informar (pedal).",
                },
                "percepcao_esforco": {
                    "type": "integer",
                    "description": (
                        "Percepção de esforço de 0 a 10, só se ele informar ou se der "
                        "para inferir com clareza do relato."
                    ),
                },
            },
            "required": ["data", "relato"],
        },
    },
    {
        "name": "configurar_cinta_fc",
        "description": (
            "Define se o atleta usa cinta cardíaca. USE quando ele disser que NÃO tem/não usa "
            "cinta cardíaca (ou que voltou a usar). Com usa_cinta=false, todo treino novo passa a "
            "ser avaliado sem FC automaticamente. Informe reavaliar_ultimos_dias para também "
            "refazer as avaliações recentes que foram feitas com a FC ruim."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "usa_cinta": {
                    "type": "boolean",
                    "description": "false = atleta não usa cinta cardíaca; true = usa.",
                },
                "reavaliar_ultimos_dias": {
                    "type": "integer",
                    "description": "Opcional: reavalia os treinos dos últimos N dias (ex.: 14). 0 = não reavaliar.",
                },
            },
            "required": ["usa_cinta"],
        },
        # Marca o fim do bloco cacheável: a lista de ferramentas nunca muda,
        # então fica cacheada (leitura ~10% do preço) em toda chamada seguinte.
        "cache_control": {"type": "ephemeral"},
    },
]


async def get_historico(user_id: str, limite: int = _MAX_HISTORICO_IA) -> list[dict]:
    db = get_db()
    doc = await db.chat_historico.find_one({"user_id": user_id})
    if not doc:
        return []
    return doc.get("mensagens", [])[-limite:]


# ── Quota semanal de perguntas ───────────────────────────────────────────────
# O admin define `features.chat_limite_semana` por usuário; ausente = ilimitado.
# O uso fica em db.chat_uso, um doc por (user_id, semana) — a virada de segunda
# zera naturalmente porque a chave da semana muda.

def _semana_atual_iso() -> str:
    hoje = datetime.now(_TZ).date()
    return (hoje - timedelta(days=hoje.weekday())).isoformat()


LIMITE_PADRAO_SEMANA = 20
"""Teto de perguntas para quem o admin não configurou à mão.

Antes a ausência de configuração significava **ilimitado** — uma bomba de custo
silenciosa: a R$ 0,086 por pergunta, só o chat pode comer metade dos R$ 24,99
antes de somar o parecer em Opus e a geração de semana. 20/semana são quase 3
por dia (4× o que a landing prometia) e, no teto, ~30% da mensalidade.

Para liberar alguém de verdade, o admin ainda pode: `chat_limite_semana: 0`
significa sem teto.
"""


async def quota_chat(user_id: str) -> dict:
    """Status da quota: {limite, usadas, restantes}. limite None = ilimitado."""
    from app.services.user_service import get_por_id
    u = await get_por_id(user_id) or {}
    features = u.get("features") or {}
    limite = features.get("chat_limite_semana")

    if limite == 0:
        return {"limite": None, "usadas": 0, "restantes": None}   # liberado pelo admin
    if not isinstance(limite, int) or limite < 0:
        limite = LIMITE_PADRAO_SEMANA
    db = get_db()
    doc = await db.chat_uso.find_one(
        {"user_id": user_id, "semana_inicio": _semana_atual_iso()})
    usadas = int((doc or {}).get("perguntas", 0))
    return {"limite": limite, "usadas": usadas, "restantes": max(limite - usadas, 0)}


async def registrar_pergunta_chat(user_id: str) -> None:
    db = get_db()
    await db.chat_uso.update_one(
        {"user_id": user_id, "semana_inicio": _semana_atual_iso()},
        {"$inc": {"perguntas": 1}},
        upsert=True,
    )


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


def _linhas_treinos(treinos: list[dict], desc_max: int = 80) -> list[str]:
    """Formata os treinos de uma semana para o chat ler.

    Um dia pode render mais de uma linha: o treino principal, o sub-bloco de
    academia (campo `academia`) e os "extras" (origem="extra"). Achatar os três
    numa lista simples fazia o chat ler um extra como se fosse o treino do dia
    e nunca enxergar a academia acoplada a um dia de bike.
    """
    linhas: list[str] = []
    # Primário antes dos extras da mesma data (False < True na ordenação).
    for t in sorted(treinos, key=lambda x: (x.get("data") or "", x.get("origem") == "extra")):
        data = t.get("data") or ""
        tipo = t.get("tipo") or "DESCANSO"
        marca = "EXTRA " if t.get("origem") == "extra" else ""
        resultado = t.get("resultado") or {}

        if resultado.get("duracao_min"):
            linha = f"  {data} [{tipo}] {marca}REALIZADO {resultado['duracao_min']}min"
            if resultado.get("distancia_km"):
                linha += f" {resultado['distancia_km']}km"
            nota = (resultado.get("analise_ia") or {}).get("nota")
            if nota is not None:
                linha += f" (nota {nota})"
            if resultado.get("origem") == "relato_atleta":
                linha += " [relatado pelo atleta, sem dispositivo]"
            elif resultado.get("fc_invalida"):
                linha += " [FC ignorada]"
        elif tipo == "DESCANSO":
            linha = f"  {data} DESCANSO"
        else:
            linha = f"  {data} [{tipo}] {marca}PLANEJADO"
            if t.get("duracao_min"):
                linha += f" {t['duracao_min']}min"
            if t.get("distancia_km"):
                linha += f" {t['distancia_km']}km"

        desc = " ".join((t.get("descricao") or "").split())
        if desc:
            linha += f" — {desc[:desc_max]}"
        linhas.append(linha)

        ac = t.get("academia") or {}
        ac_desc = " ".join((ac.get("descricao") or "").split())
        if ac_desc:
            ac_dur = f" {ac['duracao_min']}min" if ac.get("duracao_min") else ""
            linhas.append(f"    + ACADEMIA{ac_dur} no mesmo dia — {ac_desc[:desc_max]}")

    return linhas


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
        "",
        "== PLANEJAR ≠ REGISTRAR ==",
        "adicionar_treino, remover_treino e mover_treino mexem no PLANO — só para o que ainda "
        "vai acontecer.",
        "Quando o atleta disser que JÁ FEZ um treino e ele não apareceu pelo Garmin/Strava, "
        "chame registrar_treino_realizado com o relato dele. NUNCA use adicionar_treino para "
        "isso: além de não registrar nada como feito, ele reescreve a descrição do dia e apaga "
        "a prescrição planejada.",
        "",
        "== NUNCA INVENTE ==",
        "Só afirme que registrou, alterou ou removeu algo depois que a ferramenta confirmou. Se "
        "a ferramenta devolver erro, diga o que falhou — nunca diga que deu certo.",
        "O calendário abaixo é a única fonte de verdade sobre o que está planejado. Não invente "
        "treinos que não estão nele, nem descreva de memória algo que 'você tinha planejado'.",
        "Um dia de ACADEMIA é só academia: o gerador de plano nunca coloca bike e academia no "
        "mesmo dia. Quando um dia de bike também tem musculação, ela aparece na linha "
        "'+ ACADEMIA' logo abaixo do treino daquele dia.",
        "",
        "== FREQUÊNCIA CARDÍACA NÃO CONFIÁVEL ==",
        "Se o atleta disser que a FC de um treino não vale (cinta sem bateria, bateria fraca, "
        "cinta solta, esqueceu/não usou a cinta, FC travada ou absurda), NÃO responda só com "
        "texto: chame reavaliar_treino com ignorar_fc=true para aquela data — a nota e a análise "
        "são refeitas ignorando a FC e o TSS por FC.",
        "Se ele disser que NÃO tem/não usa cinta cardíaca (de modo geral), chame "
        "configurar_cinta_fc com usa_cinta=false, e use reavaliar_ultimos_dias (ex.: 14) para "
        "corrigir as avaliações recentes.",
        "Se ele não disser a data, entenda pelo contexto ('o treino de ontem', 'o de hoje') e "
        "confirme a data na resposta. Só pergunte se estiver realmente ambíguo.",
        "Depois de reavaliar, informe a nova nota e o que mudou.",
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
            if prefs.get("sem_cinta_fc"):
                linhas.append("Cinta cardíaca: NÃO usa — os treinos já são avaliados sem FC.")
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

        hoje_dt = datetime.now(_TZ).date()
        hoje_str = hoje_dt.isoformat()
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
            linhas.extend(_linhas_treinos(treinos))
    except Exception:
        pass

    return "\n".join(linhas)


async def _cancelar_no_garmin(user_id: str, ids: list) -> None:
    """Remove do calendário Garmin os workouts que foram desanexados por uma
    remoção/movimentação no chat.

    Sem isto, o agendamento antigo permanece no Garmin e o pull seguinte
    (sync_treinos_planejados) o re-importa — o treino "volta como antes".
    Best-effort: falhas (ex.: usuário sem Garmin conectado) só são logadas e
    não quebram a resposta do chat.
    """
    ids = [i for i in ids if i]
    if not ids:
        return
    try:
        from app.services.garmin_workout_service import deletar_workout_garmin
        for gid in ids:
            await deletar_workout_garmin(user_id, gid)
    except Exception as exc:
        logger.warning("Chat: falha ao cancelar workout(s) no Garmin %s: %s", ids, exc)


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
            return "\n".join(_linhas_treinos(treinos, desc_max=120))

        elif nome == "adicionar_treino":
            resultado = await criar_treino_dia(
                user_id,
                args["data"],
                args["tipo"],
                args.get("duracao_min", 60),
                args.get("descricao"),
            )
            # Se substituiu um treino que já estava agendado no Garmin, cancela o antigo.
            await _cancelar_no_garmin(user_id, [resultado.get("garmin_id_antigo")])
            return f"Treino adicionado: {args['data']} [{args['tipo']}] {args.get('duracao_min', 60)}min"

        elif nome == "remover_treino":
            resultado = await remover_treino_dia(user_id, args["data"])
            # Remove do Garmin o workout que ficou órfão (o banco já zerou o id).
            await _cancelar_no_garmin(user_id, [resultado.get("garmin_id_antigo")])
            return f"Treino de {args['data']} removido (era {resultado['tipo_antigo']})."

        elif nome == "mover_treino":
            resultado = await mover_treino(
                user_id, args["origem"], args["destino"], args.get("modo", "sobrescrever")
            )
            # Cancela no Garmin os agendamentos antigos da origem e do destino.
            await _cancelar_no_garmin(user_id, [
                resultado.get("garmin_id_origem_antigo"),
                resultado.get("garmin_id_destino_antigo"),
            ])
            return f"Treino movido de {args['origem']} para {args['destino']} (modo: {args.get('modo', 'sobrescrever')})."

        elif nome == "reavaliar_treino":
            from app.services.avaliacao_service import reavaliar_treino
            ignorar = args.get("ignorar_fc", True)
            r = await reavaliar_treino(
                user_id, args["data"], bool(ignorar), args.get("motivo")
            )
            ia = r.get("analise_ia") or {}
            base = "sem considerar a FC" if r["fc_invalida"] else "considerando a FC"
            partes = [
                f"Treino de {r['data']} ({r.get('tipo') or '—'}) reavaliado {base}.",
                f"Nova nota: {r['nota']}" if r.get("nota") is not None else "",
                f"Resumo: {ia.get('resumo')}" if ia.get("resumo") else "",
            ]
            if ia.get("pontos_fracos"):
                partes.append("A melhorar: " + "; ".join(ia["pontos_fracos"]))
            if r.get("tss_obtido") is not None:
                partes.append(f"TSS obtido: {r['tss_obtido']}")
            elif r["fc_invalida"]:
                partes.append("TSS obtido: indisponível (dependia da FC).")
            return "\n".join(p for p in partes if p)

        elif nome == "registrar_treino_realizado":
            from app.services.avaliacao_service import registrar_realizado
            r = await registrar_realizado(
                user_id,
                args["data"],
                args.get("duracao_min"),
                args.get("relato"),
                args.get("distancia_km"),
                args.get("percepcao_esforco"),
            )
            ia = r.get("analise_ia") or {}
            partes = [
                f"Treino de {r['data']} ({r.get('tipo') or '—'}) marcado como REALIZADO "
                f"({r['duracao_min']}min) a partir do relato do atleta. O treino planejado "
                f"do dia foi preservado.",
                f"Nota: {r['nota']}" if r.get("nota") is not None else "",
                f"Resumo: {ia.get('resumo')}" if ia.get("resumo") else "",
            ]
            if ia.get("pontos_fortes"):
                partes.append("Pontos fortes: " + "; ".join(ia["pontos_fortes"]))
            if ia.get("pontos_fracos"):
                partes.append("A melhorar: " + "; ".join(ia["pontos_fracos"]))
            partes.append(
                "Sem dispositivo não há TSS nem dados de FC para esta sessão — não cite "
                "zonas, bpm nem TSS obtido."
            )
            return "\n".join(p for p in partes if p)

        elif nome == "configurar_cinta_fc":
            from app.services.avaliacao_service import (
                definir_uso_cinta, reavaliar_treinos_recentes,
            )
            usa = bool(args.get("usa_cinta"))
            await definir_uso_cinta(user_id, usa)
            msg = (
                "Perfil atualizado: o atleta USA cinta cardíaca — a FC volta a contar nas avaliações."
                if usa else
                "Perfil atualizado: o atleta NÃO usa cinta cardíaca — todo treino novo será "
                "avaliado sem FC."
            )
            dias = int(args.get("reavaliar_ultimos_dias") or 0)
            if dias > 0:
                feitos = await reavaliar_treinos_recentes(user_id, dias, not usa)
                if feitos:
                    notas = ", ".join(
                        f"{f['data']}: {f['nota']}" for f in feitos if f.get("nota") is not None
                    )
                    msg += f"\n{len(feitos)} treino(s) reavaliado(s) nos últimos {dias} dias."
                    if notas:
                        msg += f" Novas notas — {notas}."
                else:
                    msg += f"\nNenhum treino com resultado nos últimos {dias} dias para reavaliar."
            return msg

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


async def responder(user_id: str, mensagem: str) -> tuple[str, bool]:
    historico = await get_historico(user_id)
    sistema = await _build_sistema(user_id)

    messages = [
        {"role": m["role"], "content": m["texto"]}
        for m in historico
    ]
    if messages:
        # Marca o fim do histórico já salvo como bloco cacheável: ele se repete
        # inteiro a cada mensagem nova (e a cada iteração do loop de ferramentas
        # abaixo), então cachear evita reprocessar esse prefixo como input "cru".
        ultima = messages[-1]
        messages[-1] = {
            "role": ultima["role"],
            "content": [{
                "type": "text",
                "text": ultima["content"],
                "cache_control": {"type": "ephemeral"},
            }],
        }
    messages.append({"role": "user", "content": mensagem})

    resposta = None
    ferramentas_usadas = False
    for _ in range(8):
        try:
            resp = await _client.messages.create(
                model=_MODEL,
                max_tokens=2000,
                system=[{
                    "type": "text",
                    "text": sistema,
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=messages,
                tools=_TOOLS,
            )
        except Exception:
            resposta = "Não consegui processar sua mensagem agora. Tente novamente em instantes."
            break

        await custo_ia_service.registrar(user_id, "chat", _MODEL, resp)

        if resp.stop_reason == "tool_use":
            ferramentas_usadas = True
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
    return resposta, ferramentas_usadas
