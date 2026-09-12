"""Cliente de IA do app — Gemini por padrão, Anthropic só se pedirem.

A conta da Anthropic ficou sem crédito em 12/09/2026 e o dono do app decidiu
não pagar API: o volume real (≈6 chamadas/dia) cabe folgado no tier gratuito
do Gemini. Em vez de reescrever os cinco serviços que falam com IA, este
módulo imita a fatia da interface do SDK da Anthropic que o app de fato usa
(`client.messages.create(...)` devolvendo `.content` / `.stop_reason` /
`.usage`) e traduz tudo para o SDK do Google por baixo.

Assim `chat_service`, `ai_service`, `fisiologia_service`, `adaptacao_service` e
`plano_semana_service` seguem com o mesmo código — muda só de onde vem o
`_client`. E voltar para a Anthropic é trocar `IA_PROVEDOR` no .env, sem mexer
em serviço nenhum.

Modelos: os limites do tier grátis pararam de ser publicados pelo Google; os
valores abaixo são os medidos em setembro/2026. Daí a divisão — o trabalho
pesado e raro num modelo forte de cota curta, o interativo num modelo leve de
cota larga:

    gemini-3.6-flash       ~20 req/dia   semana, parecer fisiológico, adaptação
    gemini-3.5-flash-lite ~500 req/dia   chat, análise pós-treino, nutrição
"""
from __future__ import annotations

import base64
import logging
from collections import OrderedDict
from dataclasses import dataclass, field

from config.settings import settings

logger = logging.getLogger(__name__)

MODELO_PESADO = "gemini-3.6-flash"
MODELO_LEVE = "gemini-3.5-flash-lite"

# De qual modelo Claude cada chamada vinha → para onde ela vai agora. O critério
# é frequência, não prestígio: o que roda uma vez por semana pode gastar a cota
# curta do modelo forte; o que o atleta dispara do celular, não.
_EQUIVALENCIA = (
    ("claude-opus",      MODELO_PESADO),
    ("claude-sonnet-5",  MODELO_PESADO),
    ("claude-sonnet-4",  MODELO_LEVE),
    ("claude-haiku",     MODELO_LEVE),
)

# Gemini 3.x pensa antes de responder e os tokens de pensamento saem do mesmo
# teto de saída. Um `max_tokens=300` herdado da Anthropic viraria resposta vazia
# — este piso evita que o modelo gaste a cota toda pensando e não sobre nada.
_PISO_SAIDA = 4096

# O Gemini 3.x assina cada chamada de ferramenta ("thought signature") e recusa
# a rodada seguinte se a assinatura não voltar junto com ela. O app guarda só
# id/nome/argumentos da chamada (era o que a Anthropic precisava), então o Part
# original fica aqui, indexado pelo id, e é ele que volta para o modelo — sem
# isso o loop de ferramentas do chat morre com 400 na segunda rodada.
_PARTES_DE_CHAMADA: "OrderedDict[str, object]" = OrderedDict()
_MAX_PARTES_GUARDADAS = 200


def _guardar_parte(id_chamada: str, parte) -> None:
    _PARTES_DE_CHAMADA[id_chamada] = parte
    while len(_PARTES_DE_CHAMADA) > _MAX_PARTES_GUARDADAS:
        _PARTES_DE_CHAMADA.popitem(last=False)


def modelo_equivalente(modelo: str) -> str:
    """Modelo Gemini correspondente ao nome de modelo que o serviço pediu."""
    if modelo.startswith("gemini-"):
        return modelo
    for prefixo, destino in _EQUIVALENCIA:
        if modelo.startswith(prefixo):
            return destino
    return MODELO_LEVE


# ─── Blocos de resposta (mesma forma que o SDK da Anthropic devolve) ──────────

@dataclass
class BlocoTexto:
    text: str
    type: str = "text"


@dataclass
class BlocoFerramenta:
    id: str
    name: str
    input: dict
    type: str = "tool_use"


@dataclass
class Uso:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass
class Resposta:
    content: list = field(default_factory=list)
    stop_reason: str = "end_turn"
    usage: Uso = field(default_factory=Uso)
    # Nome do modelo que realmente atendeu. `custo_ia_service.registrar` prefere
    # este campo ao nome pedido, senão a telemetria cobraria preço de Claude por
    # chamada feita no Gemini.
    modelo_real: str = MODELO_LEVE


# ─── Tradução: Anthropic → Gemini ────────────────────────────────────────────

def _texto_do_sistema(system) -> str | None:
    """`system` pode vir string ou lista de blocos com cache_control."""
    if not system:
        return None
    if isinstance(system, str):
        return system
    partes = []
    for bloco in system:
        if isinstance(bloco, str):
            partes.append(bloco)
        elif isinstance(bloco, dict) and bloco.get("type") == "text":
            partes.append(bloco.get("text") or "")
    return "\n\n".join(p for p in partes if p) or None


def _texto_do_resultado(conteudo) -> str:
    """Conteúdo de um tool_result — string ou lista de blocos."""
    if isinstance(conteudo, str):
        return conteudo
    if isinstance(conteudo, list):
        return "\n".join(
            b.get("text", "") if isinstance(b, dict) else str(b) for b in conteudo
        )
    return str(conteudo or "")


def _converter_mensagens(messages) -> list:
    from google.genai import types as gt

    # O Gemini identifica a resposta de uma ferramenta pelo NOME dela, não pelo
    # id da chamada como a Anthropic. Como o tool_use sempre aparece antes do
    # seu tool_result na mesma lista, dá para ligar um no outro na passagem.
    nome_por_id: dict[str, str] = {}
    conteudos = []

    for msg in messages:
        papel = "model" if msg.get("role") == "assistant" else "user"
        bruto = msg.get("content")
        partes = []

        if isinstance(bruto, str):
            if bruto.strip():
                partes.append(gt.Part.from_text(text=bruto))
        else:
            for bloco in bruto or []:
                if not isinstance(bloco, dict):
                    continue
                tipo = bloco.get("type")
                if tipo == "text":
                    texto = bloco.get("text") or ""
                    if texto.strip():
                        partes.append(gt.Part.from_text(text=texto))
                elif tipo == "image":
                    fonte = bloco.get("source") or {}
                    dados = fonte.get("data") or b""
                    partes.append(gt.Part.from_bytes(
                        data=base64.b64decode(dados) if isinstance(dados, str) else dados,
                        mime_type=fonte.get("media_type") or "image/jpeg",
                    ))
                elif tipo == "tool_use":
                    nome_por_id[bloco.get("id")] = bloco.get("name")
                    original = _PARTES_DE_CHAMADA.get(bloco.get("id"))
                    partes.append(original if original is not None else gt.Part.from_function_call(
                        name=bloco.get("name") or "ferramenta",
                        args=bloco.get("input") or {},
                    ))
                elif tipo == "tool_result":
                    partes.append(gt.Part.from_function_response(
                        name=nome_por_id.get(bloco.get("tool_use_id")) or "ferramenta",
                        response={"resultado": _texto_do_resultado(bloco.get("content"))},
                    ))

        if partes:
            conteudos.append(gt.Content(role=papel, parts=partes))

    return conteudos


def _converter_ferramentas(tools):
    """`input_schema` da Anthropic → `parameters` da declaração do Gemini."""
    from google.genai import types as gt

    if not tools:
        return None
    declaracoes = []
    for t in tools:
        esquema = t.get("input_schema") or {}
        # Ferramenta sem argumento: o Gemini recusa um objeto de propriedades
        # vazio, então é melhor não mandar `parameters` nenhum.
        parametros = esquema if (esquema.get("properties") or {}) else None
        declaracoes.append(gt.FunctionDeclaration(
            name=t["name"],
            description=t.get("description") or "",
            parameters=parametros,
        ))
    return [gt.Tool(function_declarations=declaracoes)]


def _resposta_de(bruta, modelo: str) -> Resposta:
    from google.genai import types as gt  # noqa: F401  (só para simetria de import)

    blocos: list = []
    candidatos = getattr(bruta, "candidates", None) or []
    conteudo = getattr(candidatos[0], "content", None) if candidatos else None
    partes = (getattr(conteudo, "parts", None) or []) if conteudo else []

    for i, parte in enumerate(partes):
        # Resumo de raciocínio não é resposta: entregar isso como texto faria o
        # `json.loads` do chamador engasgar num texto em prosa.
        if getattr(parte, "thought", False):
            continue
        chamada = getattr(parte, "function_call", None)
        if chamada is not None:
            id_chamada = getattr(chamada, "id", None) or f"{id(bruta)}_{i}"
            _guardar_parte(id_chamada, parte)
            blocos.append(BlocoFerramenta(
                id=id_chamada,
                name=chamada.name,
                input=dict(chamada.args or {}),
            ))
        elif getattr(parte, "text", None):
            blocos.append(BlocoTexto(text=parte.text))

    # Resposta vazia (bloqueio de segurança, corte por teto de saída) vira um
    # bloco de texto vazio de propósito: quem chamou espera achar `.text` e cair
    # no próprio fallback, não estourar StopIteration lá dentro.
    if not blocos:
        motivo = getattr(candidatos[0], "finish_reason", None) if candidatos else None
        logger.warning("ia_client: %s devolveu resposta vazia (finish_reason=%s)", modelo, motivo)
        blocos.append(BlocoTexto(text=""))

    m = getattr(bruta, "usage_metadata", None)
    uso = Uso(
        input_tokens=int(getattr(m, "prompt_token_count", 0) or 0) if m else 0,
        output_tokens=(
            int(getattr(m, "candidates_token_count", 0) or 0)
            + int(getattr(m, "thoughts_token_count", 0) or 0)
        ) if m else 0,
        cache_read_input_tokens=int(getattr(m, "cached_content_token_count", 0) or 0) if m else 0,
    )

    return Resposta(
        content=blocos,
        stop_reason="tool_use" if any(b.type == "tool_use" for b in blocos) else "end_turn",
        usage=uso,
        modelo_real=modelo,
    )


# ─── O cliente em si ─────────────────────────────────────────────────────────

_genai_client = None


def _cliente_genai():
    global _genai_client
    if _genai_client is None:
        from google import genai
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY não configurado")
        _genai_client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _genai_client


class _Mensagens:
    async def create(self, *, model: str, messages: list, max_tokens: int | None = None,
                     system=None, tools=None, temperature=None, thinking=None, **_):
        from google.genai import types as gt

        modelo = modelo_equivalente(model)
        config = gt.GenerateContentConfig(
            system_instruction=_texto_do_sistema(system),
            max_output_tokens=max(max_tokens or _PISO_SAIDA, _PISO_SAIDA),
            tools=_converter_ferramentas(tools),
            temperature=temperature,
        )
        bruta = await _cliente_genai().aio.models.generate_content(
            model=modelo,
            contents=_converter_mensagens(messages),
            config=config,
        )
        return _resposta_de(bruta, modelo)


class ClienteGemini:
    """Fachada com a mesma cara de `anthropic.AsyncAnthropic` para o app."""

    def __init__(self):
        self.messages = _Mensagens()


def usando_gemini() -> bool:
    escolha = (settings.IA_PROVEDOR or "").strip().lower()
    if escolha == "claude":
        return False
    if escolha == "gemini":
        return True
    # Sem escolha explícita: usa o que houver chave, preferindo o que não cobra.
    return bool(settings.GEMINI_API_KEY) or not settings.ANTHROPIC_API_KEY


def get_client():
    """Cliente de IA para os serviços. Um só ponto decide quem atende."""
    if usando_gemini():
        return ClienteGemini()
    import anthropic
    return anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
