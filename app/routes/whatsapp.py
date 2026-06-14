import logging
import re
from xml.sax.saxutils import escape

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel
from datetime import datetime
from app.services.whatsapp_service import send_message, send_plano_diario
from app.services.mongo_service import get_db
from app.models.models import PlanoAlimentar
from config.settings import settings

router = APIRouter()
logger = logging.getLogger(__name__)


def _twiml(mensagem: str) -> Response:
    """Resposta TwiML que faz o WhatsApp responder com 'mensagem'."""
    xml = (f'<?xml version="1.0" encoding="UTF-8"?>'
           f'<Response><Message>{escape(mensagem)}</Message></Response>')
    return Response(content=xml, media_type="application/xml")


def _resolver_datas_texto(texto: str) -> list[str]:
    """Resolve deterministicamente TODAS as datas citadas na mensagem, retornando-as
    na ordem em que aparecem no texto (por posição da substring).

    Reconhece: hoje/amanhã/ontem/anteontem/depois de amanhã e dias da semana
    com ajustes de "que vem"/"passada"/tempo verbal — mesma lógica do antigo
    _resolver_data_texto, mas capturando múltiplas ocorrências.

    Retorna lista de ISO dates (YYYY-MM-DD) na ordem de aparição no texto.
    Útil para "altere o treino de sábado para sexta" → [<sábado ISO>, <sexta ISO>].
    """
    from datetime import date, timedelta

    t_lower = " " + texto.lower() + " "
    hoje = date.today()
    seg_semana = hoje - timedelta(days=hoje.weekday())

    # Mapa de tokens de data fixa e dias da semana com posição no texto original
    # Cada entrada: (posição_no_texto, date_resolvida)
    encontrados: list[tuple[int, str]] = []

    # ── datas fixas (ordem importa: "depois de amanhã" antes de "amanhã") ──
    tokens_fixos = [
        ("depois de amanh", hoje + timedelta(days=2)),
        ("anteontem",       hoje - timedelta(days=2)),
        ("amanh",           hoje + timedelta(days=1)),   # amanhã / amanha
        ("ontem",           hoje - timedelta(days=1)),
        ("hoje",            hoje),
    ]
    for token, data_resolvida in tokens_fixos:
        pos = t_lower.find(token)
        if pos != -1:
            encontrados.append((pos, data_resolvida.isoformat()))

    # ── dias da semana ──
    _DIAS = [
        ("segunda", 0), ("terça", 1), ("terca", 1), ("quarta", 2),
        ("quinta", 3),  ("sexta", 4), ("sábado", 5), ("sabado", 5), ("domingo", 6),
    ]
    _vistos: set[int] = set()   # evita duplicar índice de dia (sábado/sabado)
    for nome, idx in _DIAS:
        if idx in _vistos:
            continue
        m = re.search(rf"\b{nome}\b", t_lower)
        if not m:
            continue
        _vistos.add(idx)
        alvo = seg_semana + timedelta(days=idx)
        # ajusta a semana conforme o contexto da frase
        if "que vem" in t_lower or "próxim" in t_lower or "proxim" in t_lower:
            alvo += timedelta(days=7)
        elif "passad" in t_lower:
            alvo -= timedelta(days=7)
        elif re.search(r"\b(fiz|comi|foi|fui|treinei|pedalei|comeu)\b", t_lower) and alvo > hoje:
            alvo -= timedelta(days=7)
        elif re.search(r"\b(vou|terei|ter[áa]|farei)\b", t_lower) and alvo < hoje:
            alvo += timedelta(days=7)
        encontrados.append((m.start(), alvo.isoformat()))

    # Ordena por posição de aparição e remove duplicatas de data mantendo a primeira ocorrência
    encontrados.sort(key=lambda x: x[0])
    vistas: set[str] = set()
    resultado: list[str] = []
    for _, data_iso in encontrados:
        if data_iso not in vistas:
            vistas.add(data_iso)
            resultado.append(data_iso)

    return resultado


def _resolver_data_texto(texto: str) -> str | None:
    """Compat: retorna a PRIMEIRA data citada no texto, ou None.
    Reimplementado em cima de _resolver_datas_texto."""
    datas = _resolver_datas_texto(texto)
    return datas[0] if datas else None


def _ref_datas() -> str:
    """Texto com as datas de referência (hoje/amanhã/ontem + dias da semana atual)
    para a IA resolver expressões como 'quinta' ou 'amanhã'."""
    from datetime import date, timedelta
    nomes = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
    hoje = date.today()
    seg = hoje - timedelta(days=hoje.weekday())
    linhas = [f"hoje = {hoje.isoformat()} ({nomes[hoje.weekday()]}-feira)",
              f"amanhã = {(hoje + timedelta(days=1)).isoformat()}",
              f"ontem = {(hoje - timedelta(days=1)).isoformat()}"]
    for i, nm in enumerate(nomes):
        linhas.append(f"{nm} desta semana = {(seg + timedelta(days=i)).isoformat()}")
    return "\n".join(linhas)


# palavra-chave na mensagem → nome da refeição (como aparece no plano)
_REFEICOES_KW = [
    (("janta", "jantar", "à noite", "a noite", "ceia"), "Jantar"),
    (("almoç", "almoc"), "Almoço"),
    (("lanche", "tarde"), "Lanche da tarde"),
    (("café da manhã", "cafe da manha", "café", "cafe", "manhã", "manha", "desjejum"), "Café da manhã"),
]


def _refeicao_pedida(texto: str) -> str | None:
    """Detecta se a mensagem pede UMA refeição específica (jantar, almoço...).
    Retorna o nome da refeição ou None (= dia todo)."""
    t = texto.lower()
    for kws, nome in _REFEICOES_KW:
        if any(k in t for k in kws):
            return nome
    return None


async def _plano_do_dia_msg(data: str, refeicao: str | None = None) -> str:
    from app.services.config_service import get_horarios, ajuste_do_dia
    from app.services.nutricao_service import (
        plano_para_tipo, formatar_plano_whatsapp, formatar_refeicao_whatsapp)
    from app.routes.nutrition import _tipo_periodo_do_dia
    cfg = await get_horarios()
    tipo, periodo = await _tipo_periodo_do_dia(data)
    ajuste = await ajuste_do_dia(data)
    extras = ajuste["extras"]
    corte = ajuste["corte_kcal"]   # None = doc legado → usa fallback de extras
    plano = plano_para_tipo(tipo, data, cfg, periodo=periodo, extras=extras, corte_kcal=corte)
    if refeicao:
        msg = formatar_refeicao_whatsapp(data, plano, refeicao)
        if msg:
            return msg
    return formatar_plano_whatsapp(data, plano)


async def _treino_do_dia_msg(data: str) -> str:
    from datetime import datetime, timedelta
    d = datetime.fromisoformat(data).date()
    seg = d - timedelta(days=d.weekday())
    dias = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    cab = f"🚴 *Treino de {dias[d.weekday()]}, {d.strftime('%d/%m')}*"
    doc = await get_db().semanas.find_one({"semana_inicio": seg.isoformat()})
    if doc:
        for t in doc.get("treinos", []):
            if t.get("data") == data:
                tipo = t.get("tipo") or "DESCANSO"
                if tipo == "DESCANSO":
                    return cab + "\n🛌 Descanso — sem treino."
                partes = [cab, f"Tipo: {tipo.replace('_', ' ').title()}"]
                if t.get("duracao_min"):  partes.append(f"⏱️ {t['duracao_min']} min")
                if t.get("distancia_km"): partes.append(f"📏 {t['distancia_km']} km")
                if t.get("cadencia_rpm"): partes.append(f"🔄 {t['cadencia_rpm']} rpm")
                if t.get("descricao"):    partes.append(f"📝 {t['descricao']}")
                return "\n".join(partes)
    return cab + "\n🛌 Sem treino marcado (descanso)."


async def _registrar_fuga_msg(extra: dict, data: str) -> str:
    from app.routes.nutrition import registrar_fuga_rollover, _montar_cabecalho_rollover
    breakdown = await registrar_fuga_rollover(data, extra)
    cabecalho = _montar_cabecalho_rollover(extra, breakdown, data)
    return cabecalho + await _plano_do_dia_msg(data)


def _fmt_data(data_iso: str) -> str:
    """Formata ISO date como dd/mm para usar nas mensagens ao usuário."""
    try:
        d = datetime.strptime(data_iso, "%Y-%m-%d")
        return d.strftime("%d/%m")
    except Exception:
        return data_iso


def _validar_ou_hoje(data_str: str | None, hoje: str) -> str:
    """Retorna data_str se for ISO válida, ou hoje caso contrário."""
    if not data_str or str(data_str).lower() == "null":
        return hoje
    try:
        datetime.fromisoformat(data_str)
        return data_str
    except (ValueError, TypeError):
        return hoje


def _dias_afetados_move(resultado: dict) -> list[dict]:
    """Monta a lista de dias afetados (origem e destino) a partir do retorno de
    mover_treino, anexando a cada dia o garmin_id antigo a ser removido."""
    origem = {**resultado["origem"], "garmin_id_antigo": resultado.get("garmin_id_origem_antigo")}
    destino = {**resultado["destino"], "garmin_id_antigo": resultado.get("garmin_id_destino_antigo")}
    return [origem, destino]


async def _sync_garmin_e_whatsapp(
    dias_afetados: list[dict],
    semana_inicio: str,
) -> str:
    """Sincroniza os dias afetados no Garmin e envia o resumo da semana no WhatsApp.

    dias_afetados: lista de dicts, um por dia que mudou de estado. Cada item:
      {"data", "tipo", "duracao_min", "descricao", "garmin_id_antigo"}.
      Para cada dia: remove o workout antigo do Garmin (se houver garmin_id_antigo)
      e, se o dia passou a ter treino real (tipo != DESCANSO e duração), faz upload
      do novo. Isso cobre mover-para-vazio, sobrescrever E swap (dois dias com treino).
    semana_inicio: ISO da segunda-feira da semana (para buscar treinos atualizados).

    Retorna string de status para compor a mensagem de confirmação.
    """
    from app.services.garmin_workout_service import upload_e_agendar, deletar_workout_garmin
    from app.services.whatsapp_service import send_semana_treinos
    from app.services.treino_semana_service import get_treinos_semana
    from app.services.mongo_service import get_db

    db = get_db()
    houve_upload = False
    houve_falha = False

    for dia in dias_afetados or []:
        data_iso = dia.get("data")

        # ── remove o workout antigo do dia (se havia um agendado no Garmin) ──
        gid_antigo = dia.get("garmin_id_antigo")
        if gid_antigo:
            ok_del = await deletar_workout_garmin(gid_antigo)
            if not ok_del:
                logger.warning("Não foi possível remover workout Garmin id=%s", gid_antigo)

        # ── faz upload do novo treino, se o dia ficou com treino real ──
        tipo = dia.get("tipo")
        duracao_min = dia.get("duracao_min")
        descricao = dia.get("descricao")
        if tipo and tipo != "DESCANSO" and duracao_min:
            nome = f"{tipo.replace('_', ' ')} — {data_iso}"
            sem_inicio = _semana_inicio_de(data_iso)
            try:
                gid = await upload_e_agendar(
                    tipo=tipo,
                    duracao_min=duracao_min,
                    nome=nome,
                    data_iso=data_iso,
                    descricao=descricao,
                )
                if gid:
                    await db.semanas.update_one(
                        {"semana_inicio": sem_inicio, "treinos.data": data_iso},
                        {"$set": {"treinos.$.garmin_workout_id": gid}},
                    )
                    houve_upload = True
                else:
                    houve_falha = True
            except Exception as e:
                logger.error("_sync_garmin_e_whatsapp: upload falhou (%s) — %s", data_iso, e)
                houve_falha = True

    if houve_falha:
        garmin_status = "⚠️ Não consegui sincronizar tudo com o Garmin (confira pelo portal)."
    elif houve_upload:
        garmin_status = "Já mandei pro Garmin 📲"
    else:
        garmin_status = ""

    # ── envia resumo da semana no WhatsApp ──
    try:
        treinos = await get_treinos_semana(semana_inicio)
        await send_semana_treinos(semana_inicio, treinos)
    except Exception as e:
        logger.error("_sync_garmin_e_whatsapp: send_semana_treinos falhou — %s", e)

    return garmin_status


def _semana_inicio_de(data_iso: str) -> str:
    """Segunda-feira (ISO) da semana de data_iso."""
    from datetime import timedelta
    d = datetime.strptime(data_iso, "%Y-%m-%d").date()
    return (d - timedelta(days=d.weekday())).isoformat()


async def _aplicar_estado_pendente(
    from_: str,
    estado: dict,
    resposta_usuario: str,
    hoje: str,
) -> Response | None:
    """Tenta interpretar a mensagem como resposta à pergunta de colisão pendente.

    Retorna Response TwiML se a mensagem foi tratada como resposta, ou None
    se não foi reconhecida (nesse caso o caller deve limpar o estado e prosseguir
    com o fluxo normal de classificação de intenção).
    """
    from app.services.treino_semana_service import (
        mover_treino, criar_treino_dia, limpar_estado, get_treinos_semana,
    )

    t = resposta_usuario.lower()
    acao = estado.get("acao")
    payload = estado.get("payload", {})

    # Detecta intenção de cancelamento
    if any(k in t for k in ("cancelar", "não", "nao", "deixa", "esquece")):
        await limpar_estado(from_)
        return _twiml("Ok, cancelei! 😊 Qualquer coisa é só falar.")

    # Detecta modo de resolução
    modo = None
    if any(k in t for k in ("trocar", "troca", "swap", "1")):
        modo = "swap"
    elif any(k in t for k in ("sobrescrever", "substituir", "sobreescrever", "2")):
        modo = "sobrescrever"

    if modo is None:
        # Não reconheceu a resposta — limpa o estado e devolve None para seguir o fluxo normal
        await limpar_estado(from_)
        logger.info("_aplicar_estado_pendente: resposta não reconhecida ('%s'), limpando estado", t)
        return None

    # ── aplica a ação com o modo escolhido ──
    await limpar_estado(from_)

    try:
        if acao == "alterar_treino":
            origem_iso = payload["origem_iso"]
            destino_iso = payload["destino_iso"]
            resultado = await mover_treino(origem_iso, destino_iso, modo)
            semana_inicio = _semana_inicio_de(destino_iso)

            tipo_origem = payload.get("tipo_origem", "")

            # Sincroniza ambos os dias afetados (cobre swap, onde os dois ficam
            # com treino, e sobrescrever, onde a origem vira descanso).
            garmin_status = await _sync_garmin_e_whatsapp(
                _dias_afetados_move(resultado), semana_inicio)

            if modo == "swap":
                tipo_destino = payload.get("tipo_destino", "")
                msg = (f"✅ Feito! Troquei os treinos:\n"
                       f"• {_fmt_data(origem_iso)} ficou com {tipo_destino.replace('_', ' ').title() if tipo_destino else 'o treino anterior do destino'}\n"
                       f"• {_fmt_data(destino_iso)} ficou com {tipo_origem.replace('_', ' ').title()}")
            else:
                msg = (f"✅ Pronto! Movi o treino de {tipo_origem.replace('_', ' ').title()} "
                       f"de {_fmt_data(origem_iso)} para {_fmt_data(destino_iso)}.")

            if garmin_status:
                msg += f"\n{garmin_status}"
            return _twiml(msg)

        elif acao == "criar_treino":
            data_iso = payload["data_iso"]
            tipo = payload["tipo"]
            duracao_min = payload["duracao_min"]
            descricao = payload.get("descricao")
            semana_inicio = _semana_inicio_de(data_iso)

            resultado = await criar_treino_dia(data_iso, tipo, duracao_min, descricao, modo=modo)
            garmin_status = await _sync_garmin_e_whatsapp([resultado], semana_inicio)

            horas = duracao_min // 60
            mins = duracao_min % 60
            dur_str = f"{horas}h{mins:02d}" if horas else f"{mins} min"
            msg = f"✅ Criei o treino de {tipo.replace('_', ' ').title()} ({dur_str}) no {_fmt_data(data_iso)}."
            if garmin_status:
                msg += f"\n{garmin_status}"
            return _twiml(msg)

    except Exception as e:
        logger.error("_aplicar_estado_pendente: erro ao aplicar acao=%s modo=%s — %s", acao, modo, e)
        return _twiml("❌ Ocorreu um erro ao aplicar a alteração. Tenta de novo ou usa o portal.")

    return None


@router.post("/webhook")
async def whatsapp_webhook(request: Request):
    """Assistente de WhatsApp: entende a intenção (cardápio/treino de um dia,
    registrar fuga por texto ou foto, trocar alimento, alterar/criar treino,
    conversar) e responde."""
    from datetime import datetime
    form = await request.form()

    # validação de assinatura da Twilio (o webhook é público)
    if settings.VALIDAR_TWILIO and settings.TWILIO_AUTH_TOKEN:
        try:
            from twilio.request_validator import RequestValidator
            validator = RequestValidator(settings.TWILIO_AUTH_TOKEN)
            if not validator.validate(str(request.url), dict(form), request.headers.get("X-Twilio-Signature", "")):
                logger.warning("Webhook WhatsApp: assinatura Twilio inválida (url=%s)", request.url)
                return Response(status_code=403, content="assinatura inválida")
        except Exception as e:
            logger.error("Webhook WhatsApp: erro na validação: %s", e)
            return Response(status_code=403, content="erro de validação")

    body = (form.get("Body") or "").strip()
    from_number = form.get("From") or "default"
    try:
        num_media = int(form.get("NumMedia") or 0)
    except ValueError:
        num_media = 0
    hoje = datetime.now().date().isoformat()

    from app.services.ai_service import estimar_alimento_extra, interpretar_mensagem, QuotaExcedida

    # FOTO → sempre tratada como fuga (comida fotografada), no dia de hoje
    if num_media > 0 and form.get("MediaUrl0"):
        img_bytes = None
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as cli:
                r = await cli.get(form.get("MediaUrl0"),
                                  auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN))
                r.raise_for_status()
                img_bytes = r.content
        except Exception as e:
            logger.error("Webhook WhatsApp: falha ao baixar mídia: %s", e)
            return _twiml("Não consegui abrir a foto. Tenta de novo ou descreve por texto.")
        try:
            extra = await estimar_alimento_extra(body or None, img_bytes, form.get("MediaContentType0"))
        except QuotaExcedida:
            return _twiml("⚠️ A IA está sem cota agora. Tenta mais tarde ou registra pelo portal.")
        except Exception as e:
            logger.error("Webhook foto: %s", e)
            return _twiml("Não consegui calcular as calorias da foto. Descreve o que era?")
        return _twiml(await _registrar_fuga_msg(extra, hoje))

    if not body:
        return _twiml("🚴 Oi! Sou teu assistente. Posso te dizer o *cardápio* ou o *treino* de um dia, "
                      "registrar o que você *comeu fora do plano* (texto ou foto), trocar alimentos, "
                      "e ainda *alterar ou criar treinos*. Manda aí!")

    # ── VERIFICAÇÃO DE ESTADO PENDENTE (colisão aguardando confirmação) ──────
    from app.services.treino_semana_service import (
        get_estado, set_estado, limpar_estado,
        mover_treino, criar_treino_dia, get_treino, get_treinos_semana,
    )

    estado = await get_estado(from_number)
    if estado:
        resp = await _aplicar_estado_pendente(from_number, estado, body, hoje)
        if resp is not None:
            return resp
        # resp = None → mensagem não reconhecida como resposta de colisão;
        # o estado já foi limpo dentro de _aplicar_estado_pendente; segue normal.

    # TEXTO → classifica a intenção
    try:
        interp = await interpretar_mensagem(body, _ref_datas())
    except QuotaExcedida:
        return _twiml("⚠️ A IA está sem cota agora. Tenta de novo mais tarde.")
    except Exception as e:
        logger.error("Webhook interpretar: %s", e)
        return _twiml("Não entendi bem 🤔 Ex.: 'cardápio de hoje', 'treino de quinta', 'comi um pão de queijo'.")

    intencao = interp.get("intencao", "conversa")

    # ── ALTERAR TREINO ────────────────────────────────────────────────────────
    if intencao == "alterar_treino":
        # Resolução determinística de duas datas: origem (1ª) e destino (2ª)
        datas_resolvidas = _resolver_datas_texto(body)
        origem_iso = datas_resolvidas[0] if len(datas_resolvidas) >= 1 else None
        destino_iso = datas_resolvidas[1] if len(datas_resolvidas) >= 2 else None

        # Fallback para campos da IA se a resolução determinística não encontrou
        if not origem_iso:
            origem_iso = _validar_ou_hoje(interp.get("data"), hoje)
        if not destino_iso:
            destino_iso = _validar_ou_hoje(interp.get("data_destino"), None) if interp.get("data_destino") else None

        if not origem_iso or not destino_iso:
            return _twiml("De qual dia pra qual dia você quer mover o treino? 🤔 "
                          "Ex.: 'muda o treino de sábado pra sexta'.")

        if origem_iso == destino_iso:
            return _twiml("Os dois dias são o mesmo 😅 Informa de um dia pra outro diferente.")

        # Verifica se há treino na origem
        treino_origem = await get_treino(origem_iso)
        if not treino_origem:
            return _twiml(f"Não encontrei nenhum treino em {_fmt_data(origem_iso)} para mover. 🛌")

        # Verifica colisão no destino
        treino_destino = await get_treino(destino_iso)
        tipo_origem = treino_origem.get("tipo", "")

        if treino_destino:
            # Há colisão — salva estado e pergunta
            tipo_destino = treino_destino.get("tipo", "")
            await set_estado(from_number, "alterar_treino", {
                "origem_iso": origem_iso,
                "destino_iso": destino_iso,
                "tipo_origem": tipo_origem,
                "tipo_destino": tipo_destino,
            })
            return _twiml(
                f"⚠️ {_fmt_data(destino_iso)} já tem um treino de "
                f"{tipo_destino.replace('_', ' ').title()}.\n"
                f"Quer *trocar* os dois dias ou *sobrescrever* o de {_fmt_data(destino_iso)}?\n"
                f"(responda: trocar / sobrescrever / cancelar)"
            )

        # Sem colisão — aplica direto (sobrescrever é equivalente a mover para dia vazio)
        try:
            resultado = await mover_treino(origem_iso, destino_iso, "sobrescrever")
        except ValueError as e:
            return _twiml(f"❌ {e}")
        except Exception as e:
            logger.error("alterar_treino sem colisão: %s", e)
            return _twiml("❌ Erro ao mover o treino. Tenta de novo.")

        semana_inicio = _semana_inicio_de(destino_iso)
        garmin_status = await _sync_garmin_e_whatsapp(
            _dias_afetados_move(resultado), semana_inicio)

        msg = (f"✅ Pronto! Movi o treino de {tipo_origem.replace('_', ' ').title()} "
               f"de {_fmt_data(origem_iso)} para {_fmt_data(destino_iso)}.")
        if garmin_status:
            msg += f"\n{garmin_status}"
        return _twiml(msg)

    # ── CRIAR TREINO ──────────────────────────────────────────────────────────
    if intencao == "criar_treino":
        # Resolve data deterministicamente
        datas_resolvidas = _resolver_datas_texto(body)
        data_iso = datas_resolvidas[0] if datas_resolvidas else None
        if not data_iso:
            data_iso = _validar_ou_hoje(interp.get("data"), hoje)

        # Duração: tenta extrair da IA (ela é boa para parsear "três horas")
        duracao_min = None
        try:
            duracao_min = int(interp.get("duracao_min") or 0) or None
        except (ValueError, TypeError):
            duracao_min = None

        # Fallback: tenta parsear direto do texto (ex.: "3h", "1h30", "90 min")
        if not duracao_min:
            m_dur = re.search(r"(\d+)\s*h(?:oras?)?\s*(\d+)?|(\d+)\s*min", body.lower())
            if m_dur:
                if m_dur.group(1):
                    hh = int(m_dur.group(1))
                    mm = int(m_dur.group(2) or 0)
                    duracao_min = hh * 60 + mm
                elif m_dur.group(3):
                    duracao_min = int(m_dur.group(3))

        if not duracao_min:
            return _twiml("Qual a duração do treino? ⏱️ Ex.: '3 horas', '90 min', '1h30'.")

        # Tipo: da IA; padrão Z2_LONGO
        tipo = str(interp.get("tipo") or "Z2_LONGO").upper()
        _TIPOS_VALIDOS = {"Z2_LONGO", "TIROS", "VO2MAX", "TEMPO", "FORCA", "RECUPERACAO"}
        if tipo not in _TIPOS_VALIDOS:
            tipo = "Z2_LONGO"

        descricao = interp.get("descricao") or tipo.replace("_", " ").title()

        # Verifica colisão
        treino_existente = await get_treino(data_iso)
        if treino_existente:
            tipo_existente = treino_existente.get("tipo", "")
            await set_estado(from_number, "criar_treino", {
                "data_iso": data_iso,
                "tipo": tipo,
                "duracao_min": duracao_min,
                "descricao": descricao,
                "tipo_existente": tipo_existente,
            })
            return _twiml(
                f"⚠️ {_fmt_data(data_iso)} já tem um treino de "
                f"{tipo_existente.replace('_', ' ').title()}.\n"
                f"Quer *sobrescrever* com o novo treino de {tipo.replace('_', ' ').title()}?\n"
                f"(responda: sobrescrever / cancelar)\n"
                f"_Ou 'trocar' para inverter os dois dias._"
            )

        # Sem colisão — grava direto
        try:
            resultado = await criar_treino_dia(data_iso, tipo, duracao_min, descricao)
        except Exception as e:
            logger.error("criar_treino: %s", e)
            return _twiml("❌ Erro ao criar o treino. Tenta de novo.")

        semana_inicio = _semana_inicio_de(data_iso)
        garmin_status = await _sync_garmin_e_whatsapp([resultado], semana_inicio)

        horas = duracao_min // 60
        mins = duracao_min % 60
        dur_str = f"{horas}h{mins:02d}" if horas else f"{mins} min"
        msg = f"✅ Criei um treino de {tipo.replace('_', ' ').title()} ({dur_str}) no {_fmt_data(data_iso)}. 🚵"
        if garmin_status:
            msg += f"\n{garmin_status}"
        return _twiml(msg)

    # ── INTENÇÕES EXISTENTES ──────────────────────────────────────────────────

    # 1) resolução determinística pelo texto (a IA erra dias da semana por 1 dia)
    data = _resolver_data_texto(body)
    # 2) fallback: data devolvida pela IA (que às vezes vem "null" ou inválida)
    if not data:
        data = interp.get("data")
        if not data or str(data).lower() == "null":
            data = hoje
        else:
            try:
                datetime.fromisoformat(data)
            except (ValueError, TypeError):
                data = hoje

    if intencao == "plano_dia":
        return _twiml(await _plano_do_dia_msg(data, _refeicao_pedida(body)))
    if intencao == "treino_dia":
        return _twiml(await _treino_do_dia_msg(data))
    if intencao in ("registrar_fuga", "trocar_alimento"):
        desc = (interp.get("para") if intencao == "trocar_alimento" else interp.get("descricao")) or body
        try:
            extra = await estimar_alimento_extra(desc, None, None)
        except QuotaExcedida:
            return _twiml("⚠️ A IA está sem cota agora. Tenta mais tarde.")
        except Exception as e:
            logger.error("Webhook fuga texto: %s", e)
            return _twiml("Não consegui calcular as calorias disso. Tenta descrever de outro jeito?")
        msg = await _registrar_fuga_msg(extra, data)
        if intencao == "trocar_alimento" and interp.get("de"):
            msg = f"🔁 Beleza, pode trocar *{interp['de']}* por *{interp['para']}*.\n" + msg
        return _twiml(msg)

    # conversa geral
    return _twiml(interp.get("resposta") or
                  "🚴 Posso te dizer o cardápio ou o treino de um dia, registrar o que comeu fora do plano "
                  "(texto/foto), trocar alimentos, e alterar ou criar treinos. É só falar!")


class MensagemBody(BaseModel):
    mensagem: str


@router.get("/", response_class=HTMLResponse)
async def ui_enviar_mensagem():
    return """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>MTB Nutrition — WhatsApp</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #f0f2f5; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
    .card { background: white; border-radius: 14px; padding: 36px; width: 100%; max-width: 500px; box-shadow: 0 4px 20px rgba(0,0,0,0.1); }
    .logo { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
    .logo h1 { color: #128c7e; font-size: 1.4rem; }
    p.sub { color: #888; font-size: 0.88rem; margin-bottom: 24px; }
    label { display: block; font-size: 0.85rem; font-weight: 600; color: #444; margin-bottom: 6px; }
    textarea { width: 100%; border: 1.5px solid #ddd; border-radius: 10px; padding: 12px; font-size: 1rem; resize: vertical; min-height: 150px; outline: none; font-family: inherit; transition: border-color 0.2s; line-height: 1.5; }
    textarea:focus { border-color: #128c7e; }
    .count { text-align: right; color: #bbb; font-size: 0.78rem; margin: 5px 0 20px; }
    button { width: 100%; padding: 14px; background: #128c7e; color: white; border: none; border-radius: 10px; font-size: 1rem; font-weight: 700; cursor: pointer; transition: background 0.2s; letter-spacing: 0.3px; }
    button:hover:not(:disabled) { background: #0a7163; }
    button:disabled { background: #b2dfdb; cursor: not-allowed; }
    .status { margin-top: 16px; padding: 12px 16px; border-radius: 10px; font-size: 0.9rem; display: none; }
    .ok  { background: #e8f5e9; color: #2e7d32; display: block; }
    .err { background: #fdecea; color: #c62828; display: block; }
  </style>
</head>
<body>
<div class="card">
  <div class="logo"><span style="font-size:1.8rem">🚵</span><h1>MTB Nutrition</h1></div>
  <p class="sub">Enviar mensagem manual via WhatsApp</p>
  <label for="msg">Mensagem</label>
  <textarea id="msg" placeholder="Digite sua mensagem aqui..." oninput="cnt()"></textarea>
  <div class="count"><span id="n">0</span> caracteres</div>
  <button id="btn" onclick="send()">📤 Enviar</button>
  <div id="st" class="status"></div>
</div>
<script>
  function cnt() { document.getElementById('n').textContent = document.getElementById('msg').value.length; }
  async function send() {
    const msg = document.getElementById('msg').value.trim();
    const btn = document.getElementById('btn');
    const st  = document.getElementById('st');
    if (!msg) { st.className='status err'; st.textContent='⚠️ Digite uma mensagem antes de enviar.'; return; }
    btn.disabled = true; btn.textContent = 'Enviando...';
    st.className = 'status'; st.textContent = '';
    try {
      const r = await fetch('/whatsapp/mensagem', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({mensagem: msg}) });
      const d = await r.json();
      if (r.ok) { st.className='status ok'; st.textContent='✅ Mensagem enviada com sucesso!'; document.getElementById('msg').value=''; cnt(); }
      else { throw new Error(d.detail || JSON.stringify(d)); }
    } catch(e) { st.className='status err'; st.textContent='❌ Erro: ' + e.message; }
    finally { btn.disabled=false; btn.textContent='📤 Enviar'; }
  }
  document.getElementById('msg').addEventListener('keydown', e => { if (e.ctrlKey && e.key === 'Enter') send(); });
</script>
</body>
</html>"""


@router.post("/mensagem")
async def enviar_mensagem(body: MensagemBody):
    mensagem = body.mensagem.strip()
    if not mensagem:
        raise HTTPException(status_code=400, detail="Mensagem não pode ser vazia")
    if not settings.WHATSAPP_TO:
        raise HTTPException(status_code=500, detail="Configure WHATSAPP_TO no .env")
    result = await send_message(settings.WHATSAPP_TO, mensagem)
    return {"status": "enviado", "result": result}


@router.post("/teste")
async def testar_whatsapp():
    if not settings.WHATSAPP_TO:
        raise HTTPException(status_code=500, detail="Configure WHATSAPP_TO no .env")
    result = await send_message(settings.WHATSAPP_TO, "✅ *MTB Nutrition Bot* — teste de conexão bem-sucedido! 🚵")
    return {"status": "enviado", "result": result}


@router.post("/send-plano")
async def enviar_plano_hoje():
    db = get_db()
    hoje = datetime.now().date()
    doc = await db.planos.find_one(
        {"data": {"$gte": datetime(hoje.year, hoje.month, hoje.day)}},
        {"_id": 0}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Nenhum plano para hoje")
    plano = PlanoAlimentar(**doc)
    result = await send_plano_diario(plano)
    return {"status": "enviado", "result": result}
