"""Adaptação da semana quando o treino do dia sai do plano.

O atleta não avisa antes: ele treina o que dá para treinar naquele dia, e o app
descobre depois — pelo que chegou do Garmin (fez diferente) ou pelo silêncio de
um dia que passou sem resultado (não fez). A partir daí quem decide os dias
seguintes é o treinador: fez VO2máx na quinta, a VO2máx da sexta não faz sentido.

Divisão de responsabilidade, a mesma da geração semanal: a IA propõe (é ela que
sabe treinar), o código valida (é ele que garante as regras que não se negociam).
Aqui só se DECIDE — aplicar no banco, no Garmin e avisar no WhatsApp é do
chamador.

Regras duras, decididas com o atleta:
- Volume perdido NÃO se repõe. A soma dos minutos restantes nunca sobe; o que
  muda é a intensidade e a ordem dos dias.
- Dia que já aconteceu é intocável (tem resultado, ou já passou).
- Dois dias duros nunca se encostam — contando o que foi FEITO, não o planejado.
- Semana de prova/descarga só aceita ajuste para baixo.
"""

import json
import logging

from app.utils import hoje_local

logger = logging.getLogger(__name__)

# Classe de carga de cada tipo. A comparação planejado × realizado é feita por
# CLASSE, não por tipo: o classificador do .fit confunde VO2máx com tiros (os
# dois são blocos em Z5) e isso não muda nada na decisão do dia seguinte — o que
# importa é que o dia foi duro.
CLASSE_CARGA = {
    "VO2MAX": "duro",
    "TIROS": "duro",
    "TESTE_FTP": "duro",
    "TEMPO": "moderado",
    "FORCA": "moderado",
    "ACADEMIA": "moderado",
    "Z2_LONGO": "facil",
    "RECUPERACAO": "facil",
    "DESCANSO": "nenhum",
}
ORDEM_CLASSE = {"nenhum": 0, "facil": 1, "moderado": 2, "duro": 3}

# Desvio de volume: só conta o que muda a sessão de verdade. 20 min a menos num
# treino de 2h é a vida real; 50 min a menos é outro treino.
_DESVIO_VOLUME_PCT = 0.35
_DESVIO_VOLUME_MIN = 20

_NOMES_DIA = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")


def classe_do_tipo(tipo: str | None) -> str:
    return CLASSE_CARGA.get((tipo or "DESCANSO").upper(), "moderado")


def _duracao_realizada(resultado: dict) -> int | None:
    dur = resultado.get("duracao_min")
    return int(dur) if dur else None


def detectar_desvio(dia: dict, hoje: str | None = None) -> dict | None:
    """O que foi feito neste dia sai do que estava prescrito?

    Retorna None quando o dia seguiu o plano (ou ainda não chegou). Caso
    contrário, um dict com o tipo de desvio — é o gatilho da adaptação.
    """
    hoje = hoje or hoje_local().isoformat()
    data = dia.get("data") or ""
    if not data or data > hoje:
        return None                      # dia futuro: não há o que comparar

    tipo_planejado = (dia.get("tipo") or "DESCANSO").upper()
    resultado = dia.get("resultado") or {}

    # 1) Silêncio: o dia passou e nada foi registrado. Só vale para dia FECHADO —
    #    hoje ainda dá tempo de treinar.
    if not resultado:
        if data >= hoje or tipo_planejado == "DESCANSO":
            return None
        return {
            "data": data,
            "motivo": "nao_fez",
            "tipo_planejado": tipo_planejado,
            "tipo_realizado": None,
            "classe_planejada": classe_do_tipo(tipo_planejado),
            "classe_realizada": "nenhum",
            "duracao_planejada": dia.get("duracao_min"),
            "duracao_realizada": None,
        }

    tipo_realizado = (resultado.get("tipo_realizado") or "").upper() or None
    classe_plan = classe_do_tipo(tipo_planejado)
    classe_real = classe_do_tipo(tipo_realizado) if tipo_realizado else None

    dur_plan = dia.get("duracao_min")
    dur_real = _duracao_realizada(resultado)

    mudou_intensidade = bool(classe_real and classe_real != classe_plan)
    mudou_volume = False
    if dur_plan and dur_real:
        dif = abs(dur_real - dur_plan)
        mudou_volume = dif >= _DESVIO_VOLUME_MIN and dif / dur_plan >= _DESVIO_VOLUME_PCT

    if not (mudou_intensidade or mudou_volume):
        return None

    if mudou_intensidade and mudou_volume:
        motivo = "trocou_o_treino"
    elif mudou_intensidade:
        motivo = "trocou_intensidade"
    else:
        motivo = "trocou_volume"

    return {
        "data": data,
        "motivo": motivo,
        "tipo_planejado": tipo_planejado,
        "tipo_realizado": tipo_realizado,
        "classe_planejada": classe_plan,
        "classe_realizada": classe_real or classe_plan,
        "duracao_planejada": dur_plan,
        "duracao_realizada": dur_real,
        "tss_obtido": resultado.get("tss_obtido"),
        "tss_esperado": resultado.get("tss_esperado"),
    }


def desvios_da_semana(treinos: list[dict], hoje: str | None = None) -> list[dict]:
    """Todos os desvios já fechados da semana, em ordem de data."""
    achados = [detectar_desvio(t, hoje) for t in treinos if t.get("origem") != "extra"]
    return sorted([d for d in achados if d], key=lambda d: d["data"])


# ── validação: o que a IA propõe não passa por cima das regras duras ──────────

def _dia_intocavel(dia: dict, hoje: str) -> bool:
    """Dia que já aconteceu não se replaneja — nem que a IA peça."""
    return bool(dia.get("data", "") <= hoje or (dia.get("resultado") or {}))


def validar_ajustes(
    ajustes: list[dict],
    treinos: list[dict],
    *,
    hoje: str | None = None,
    preferencias: dict | None = None,
    fase: str | None = None,
    estagio_taper: str | None = None,
    data_prova: str | None = None,
) -> list[dict]:
    """Filtra e corrige a proposta da IA. Devolve só o que pode ser aplicado.

    Não confia no modelo para nada que tenha consequência física: dia passado,
    volume inflado, dois dias duros grudados e semana de prova são resolvidos
    aqui, com as mesmas regras de agenda da geração semanal.
    """
    from app.services.plano_semana_service import _aplicar_regras_agenda, _TIPOS_VALIDOS

    hoje = hoje or hoje_local().isoformat()
    por_data = {t.get("data"): t for t in treinos if t.get("origem") != "extra"}

    limpos: list[dict] = []
    for aj in ajustes:
        data = aj.get("data")
        dia = por_data.get(data)
        if not dia or _dia_intocavel(dia, hoje):
            continue

        tipo = (aj.get("tipo") or dia.get("tipo") or "DESCANSO").upper()
        if tipo not in _TIPOS_VALIDOS:
            continue

        duracao = aj.get("duracao_min") or dia.get("duracao_min")
        duracao = int(duracao) if duracao else None
        descricao = aj.get("descricao") or ""
        cadencia = None if tipo == "ACADEMIA" else aj.get("cadencia_rpm")

        tipo, duracao, descricao, cadencia = _aplicar_regras_agenda(
            data, tipo, duracao, descricao, cadencia, preferencias,
            fase, estagio_taper, data_prova,
        )

        # Semana de prova/descarga: só ajuste que ALIVIA.
        if estagio_taper and _fica_mais_pesado(dia, tipo, duracao):
            continue

        if tipo == (dia.get("tipo") or "").upper() and duracao == dia.get("duracao_min") \
                and not descricao:
            continue                       # nada mudou de fato

        limpos.append({
            "data": data,
            "tipo": tipo,
            "duracao_min": duracao,
            "descricao": descricao,
            "cadencia_rpm": cadencia,
            "motivo": (aj.get("motivo") or "").strip(),
        })

    limpos = _sem_dias_duros_grudados(limpos, por_data, hoje)
    limpos = _sem_repor_volume(limpos, por_data, hoje)
    return sorted(limpos, key=lambda a: a["data"])


def _fica_mais_pesado(dia: dict, tipo: str, duracao: int | None) -> bool:
    plan_classe = ORDEM_CLASSE[classe_do_tipo(dia.get("tipo"))]
    nova_classe = ORDEM_CLASSE[classe_do_tipo(tipo)]
    if nova_classe > plan_classe:
        return True
    return bool(duracao and dia.get("duracao_min") and duracao > dia["duracao_min"])


def _sem_dias_duros_grudados(ajustes: list[dict], por_data: dict, hoje: str) -> list[dict]:
    """Dois dias duros seguidos viram dia duro + dia fácil.

    Olha o dia ANTERIOR pelo que foi REALIZADO quando ele já aconteceu: o desvio
    que disparou tudo isto é justamente um dia que virou duro sem estar no plano.
    """
    from datetime import date, timedelta

    def classe_efetiva(data: str) -> str:
        dia = por_data.get(data)
        if not dia:
            return "nenhum"
        res = dia.get("resultado") or {}
        if data <= hoje and res.get("tipo_realizado"):
            return classe_do_tipo(res["tipo_realizado"])
        pendente = next((a for a in ajustes if a["data"] == data), None)
        return classe_do_tipo((pendente or dia).get("tipo"))

    corrigidos = []
    for aj in sorted(ajustes, key=lambda a: a["data"]):
        if classe_do_tipo(aj["tipo"]) == "duro":
            anterior = (date.fromisoformat(aj["data"]) - timedelta(days=1)).isoformat()
            if classe_efetiva(anterior) == "duro":
                logger.info(
                    "adaptacao: %s viraria duro colado em %s — rebaixado para recuperação",
                    aj["data"], anterior,
                )
                aj = {**aj, "tipo": "RECUPERACAO",
                      "motivo": aj.get("motivo") or
                      "Dia anterior foi forte — hoje entra recuperação para não emendar dois dias duros."}
        corrigidos.append(aj)
    return corrigidos


def _sem_repor_volume(ajustes: list[dict], por_data: dict, hoje: str) -> list[dict]:
    """A soma dos minutos que ainda faltam na semana não pode subir.

    Regra do atleta: volume perdido não se repõe. Mover uma sessão de dia é
    permitido (o total não muda); alongar os dias que sobraram para compensar o
    treino que não aconteceu, não.
    """
    futuros = [d for dt, d in por_data.items() if dt > hoje and not (d.get("resultado") or {})]
    teto = sum(int(d.get("duracao_min") or 0) for d in futuros)

    mudados = {a["data"]: a for a in ajustes}
    proposto = sum(
        int((mudados.get(d["data"]) or d).get("duracao_min") or 0) for d in futuros
    )
    if proposto <= teto:
        return ajustes

    logger.info(
        "adaptacao: proposta somava %s min contra %s min planejados — cortando o excesso",
        proposto, teto,
    )
    # Corta o excesso dos dias que a IA alongou, do maior aumento para o menor,
    # até a semana voltar ao teto. Nunca abaixo do que o dia já tinha.
    excesso = proposto - teto
    aumentos = sorted(
        (a for a in ajustes
         if (a.get("duracao_min") or 0) > int((por_data.get(a["data"]) or {}).get("duracao_min") or 0)),
        key=lambda a: (a["duracao_min"] or 0) - int((por_data[a["data"]].get("duracao_min") or 0)),
        reverse=True,
    )
    for aj in aumentos:
        if excesso <= 0:
            break
        planejado = int(por_data[aj["data"]].get("duracao_min") or 0)
        corte = min(excesso, (aj["duracao_min"] or 0) - planejado)
        aj["duracao_min"] = (aj["duracao_min"] or 0) - corte
        excesso -= corte
    return ajustes


# ── proposta: a IA como treinador, o validador como fiscal ───────────────────

_INSTRUCAO_AJUSTE = """AJUSTE DE MEIO DE SEMANA — o atleta saiu do plano.

Você não está gerando uma semana nova: está corrigindo o resto DESTA semana para
que o atleta chegue melhor no fim dela, sabendo o que ele já fez de verdade.

REGRAS QUE NÃO SE NEGOCIAM:
1. Só pode mexer em dias DEPOIS de hoje. Dia com treino já feito é história.
2. Volume perdido NÃO se repõe: a soma dos minutos dos dias restantes não pode
   passar do que já estava planejado. O que você ajusta é a INTENSIDADE e a ORDEM.
3. Nunca deixe dois dias duros (VO2MAX, TIROS, TESTE_FTP) colados — conte o que
   foi FEITO, não o que estava no papel.
4. Mexa só no necessário. Dia que continua fazendo sentido, deixe quieto.

Responda APENAS com JSON:
{"resumo": "1 frase para o atleta, dizendo o que mudou e por quê",
 "ajustes": [{"data": "YYYY-MM-DD", "tipo": "...", "duracao_min": 90,
              "cadencia_rpm": "85-95",
              "descricao": "prescrição completa, no mesmo padrão da semana",
              "motivo": "1 frase curta: por que ESTE dia mudou"}]}
Lista vazia em "ajustes" se nada precisa mudar."""


def _linha_dia(t: dict, hoje: str) -> str:
    tipo = t.get("tipo") or "DESCANSO"
    dur = f" · {t['duracao_min']}min" if t.get("duracao_min") else ""
    res = t.get("resultado") or {}
    if res:
        feito = res.get("tipo_realizado") or "?"
        detalhe = f"FEITO: {feito} · {res.get('duracao_min') or '?'}min"
        if res.get("tss_obtido"):
            detalhe += f" · TSS {res['tss_obtido']}"
        return f"  {t['data']} → planejado {tipo}{dur} | {detalhe}"
    quando = "hoje" if t["data"] == hoje else ("passado" if t["data"] < hoje else "a fazer")
    return f"  {t['data']} → {tipo}{dur} ({quando})"


def _texto_desvio(desvio: dict) -> str:
    if desvio["motivo"] == "nao_fez":
        return (f"{desvio['data']}: o treino de {desvio['tipo_planejado']} "
                f"({desvio.get('duracao_planejada') or '?'} min) NÃO foi feito.")
    return (
        f"{desvio['data']}: estava prescrito {desvio['tipo_planejado']} "
        f"({desvio.get('duracao_planejada') or '?'} min) e o atleta fez "
        f"{desvio.get('tipo_realizado') or '?'} ({desvio.get('duracao_realizada') or '?'} min) — "
        f"carga {desvio['classe_planejada']} virou {desvio['classe_realizada']}."
    )


async def propor_ajuste(user_id: str, semana_inicio: str, desvio: dict,
                        hoje: str | None = None) -> dict | None:
    """Decide como fica o resto da semana depois do desvio.

    Retorna {"desvio", "ajustes", "resumo", "modelo"} — já validado e pronto para
    ser aplicado, ou None se não há nada a mudar. NÃO grava nada.
    """
    from app.services.mongo_service import get_db
    from app.services.plano_semana_service import (
        _client, _MODEL_PLANO, _SISTEMA_PLANO, _extrair_texto, _is_quota_error,
        _chamar_gemini, dias_treino_do_usuario,
    )
    from app.services import custo_ia_service

    hoje = hoje or hoje_local().isoformat()
    db = get_db()
    doc = await db.semanas.find_one({"semana_inicio": semana_inicio, "user_id": str(user_id)})
    if not doc:
        return None
    treinos = [t for t in doc.get("treinos", []) if t.get("origem") != "extra"]
    if not any(t.get("data", "") > hoje for t in treinos):
        return None                      # semana acabou: nada para ajustar

    user = await _perfil(user_id)
    preferencias = user.get("preferencias") or {}
    fase, estagio, data_prova = await _contexto_prova(user_id, semana_inicio)

    dias_nomes = ", ".join(_NOMES_DIA[d] for d in dias_treino_do_usuario(preferencias))
    prompt = f"""{_INSTRUCAO_AJUSTE}

HOJE: {hoje}
DIAS EM QUE O ATLETA TREINA: {dias_nomes}
{_bloco_prova_txt(fase, estagio, data_prova)}
O QUE ACONTECEU:
{_texto_desvio(desvio)}

SEMANA ({semana_inicio}):
{chr(10).join(_linha_dia(t, hoje) for t in sorted(treinos, key=lambda t: t.get('data', '')))}
"""

    modelo = _MODEL_PLANO
    try:
        resp = await _client.messages.create(
            model=_MODEL_PLANO,
            max_tokens=4000,
            system=[{"type": "text", "text": _SISTEMA_PLANO,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        )
        await custo_ia_service.registrar(user_id, "adaptar_semana", _MODEL_PLANO, resp)
        bruto = _extrair_texto(resp).strip().replace("```json", "").replace("```", "").strip()
        data = json.loads(bruto)
    except Exception as exc:
        if _is_quota_error(exc):
            try:
                bruto = await _chamar_gemini(prompt, _SISTEMA_PLANO, user_id, "adaptar_semana")
                data = json.loads(bruto.strip().replace("```json", "").replace("```", "").strip())
                modelo = "gemini"
            except Exception as eg:
                logger.warning("adaptacao: Gemini também falhou (%s) — ajuste mínimo", eg)
                data, modelo = _ajuste_minimo(desvio, treinos, hoje), "fallback"
        else:
            logger.warning("adaptacao: IA falhou (%s) — ajuste mínimo", exc)
            data, modelo = _ajuste_minimo(desvio, treinos, hoje), "fallback"

    ajustes = validar_ajustes(
        data.get("ajustes") or [], treinos,
        hoje=hoje, preferencias=preferencias,
        fase=fase, estagio_taper=estagio, data_prova=data_prova,
    )
    if not ajustes:
        return None
    return {
        "desvio": desvio,
        "ajustes": ajustes,
        "resumo": (data.get("resumo") or "").strip(),
        "modelo": modelo,
    }


async def _perfil(user_id: str) -> dict:
    from app.services.user_service import get_por_id
    return await get_por_id(user_id) or {}


async def _contexto_prova(user_id: str, semana_inicio: str):
    """(fase, estagio_taper, data_prova) da próxima prova — as mesmas regras de
    periodização que a geração semanal usa."""
    from app.services.prova_service import (
        proxima_prova, semanas_ate, fase_periodizacao, estagio_taper,
    )
    prova = await proxima_prova(user_id, ref=semana_inicio)
    if not prova:
        return None, None, None
    semanas = semanas_ate(prova["data"], ref=semana_inicio)
    return fase_periodizacao(semanas), estagio_taper(semanas), prova["data"]


def _bloco_prova_txt(fase, estagio, data_prova) -> str:
    if not data_prova:
        return ""
    linha = f"PRÓXIMA PROVA: {data_prova} (fase {fase})"
    if estagio:
        linha += f" — POLIMENTO ({estagio}): só ajuste que ALIVIA."
    return linha + "\n"


def _ajuste_minimo(desvio: dict, treinos: list[dict], hoje: str) -> dict:
    """Rede de segurança sem IA: se o atleta fez um dia duro fora do plano, o
    próximo dia duro da semana vira recuperação. Nada mais.

    Prefere-se pouco e certo a nada: sem isto, uma falha da API deixaria dois
    dias duros colados, que é exatamente o problema que a adaptação existe para
    evitar.
    """
    from app.services.plano_semana_service import _DESCRICAO_PADRAO

    if desvio.get("classe_realizada") != "duro":
        return {"resumo": "", "ajustes": []}
    seguintes = sorted((t for t in treinos if t.get("data", "") > hoje),
                       key=lambda t: t["data"])
    for t in seguintes:
        if classe_do_tipo(t.get("tipo")) == "duro":
            return {
                "resumo": "Você fez um treino forte fora do plano — o próximo dia duro virou recuperação.",
                "ajustes": [{
                    "data": t["data"],
                    "tipo": "RECUPERACAO",
                    "duracao_min": t.get("duracao_min"),
                    "descricao": _DESCRICAO_PADRAO["RECUPERACAO"],
                    "motivo": "Dia forte não planejado antes deste — sem dois duros colados.",
                }],
            }
    return {"resumo": "", "ajustes": []}
