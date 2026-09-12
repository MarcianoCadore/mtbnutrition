"""Tradução Anthropic → Gemini: o app fala uma língua só, o cliente traduz.

Os serviços continuam escritos contra a interface da Anthropic; quem atende é o
Gemini. O que estes testes protegem é a tradução — se ela escorregar, o chat
responde "não consegui processar" sem dizer por quê.
"""
import base64

import pytest

from app.services import ia_client


class TestEscolhaDeModelo:
    def test_trabalho_raro_vai_no_modelo_forte(self):
        # Cota curta (~20/dia) serve para o que roda uma vez por semana.
        assert ia_client.modelo_equivalente("claude-opus-4-8") == ia_client.MODELO_PESADO
        assert ia_client.modelo_equivalente("claude-sonnet-5") == ia_client.MODELO_PESADO

    def test_interativo_vai_no_modelo_de_cota_larga(self):
        # Chat e análise pós-treino saem do celular e não podem esbarrar em cota.
        assert ia_client.modelo_equivalente("claude-sonnet-4-6") == ia_client.MODELO_LEVE
        assert ia_client.modelo_equivalente("claude-haiku-4-5") == ia_client.MODELO_LEVE

    def test_nome_de_gemini_passa_direto(self):
        assert ia_client.modelo_equivalente("gemini-2.5-flash-lite") == "gemini-2.5-flash-lite"

    def test_modelo_desconhecido_nao_gasta_a_cota_curta(self):
        assert ia_client.modelo_equivalente("modelo-novo-qualquer") == ia_client.MODELO_LEVE


class TestSistema:
    def test_string_simples(self):
        assert ia_client._texto_do_sistema("regras") == "regras"

    def test_blocos_com_cache_control_viram_um_texto_so(self):
        # chat_service e plano_semana_service mandam o system em blocos com
        # cache_control da Anthropic; o Gemini quer uma instrução única.
        blocos = [
            {"type": "text", "text": "parte 1", "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": "parte 2"},
        ]
        assert ia_client._texto_do_sistema(blocos) == "parte 1\n\nparte 2"

    def test_vazio_vira_none(self):
        assert ia_client._texto_do_sistema(None) is None
        assert ia_client._texto_do_sistema([]) is None


class TestMensagens:
    def test_papel_assistant_vira_model(self):
        conteudos = ia_client._converter_mensagens([
            {"role": "user", "content": "oi"},
            {"role": "assistant", "content": "olá"},
        ])
        assert [c.role for c in conteudos] == ["user", "model"]

    def test_imagem_base64_vira_bytes(self):
        dados = b"\x89PNG\r\n"
        conteudos = ia_client._converter_mensagens([{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                             "data": base64.b64encode(dados).decode()}},
                {"type": "text", "text": "que zonas são essas?"},
            ],
        }])
        partes = conteudos[0].parts
        assert partes[0].inline_data.data == dados
        assert partes[0].inline_data.mime_type == "image/png"
        assert partes[1].text == "que zonas são essas?"

    def test_resultado_de_ferramenta_volta_pelo_nome_nao_pelo_id(self):
        # A Anthropic liga chamada e resposta pelo tool_use_id; o Gemini liga
        # pelo NOME da função. Sem essa tradução o modelo recebe a resposta de
        # uma ferramenta que ele não sabe qual é.
        conteudos = ia_client._converter_mensagens([
            {"role": "user", "content": "o que tenho na semana?"},
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "tu_1", "name": "ver_semana",
                 "input": {"semana_inicio": "2026-09-14"}}]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "tu_1", "content": "VO2MAX 75min"}]},
        ])
        resposta = conteudos[2].parts[0].function_response
        assert resposta.name == "ver_semana"
        assert "VO2MAX" in resposta.response["resultado"]

    def test_mensagem_vazia_nao_vira_conteudo(self):
        # O Gemini recusa Content sem parte nenhuma.
        assert ia_client._converter_mensagens([{"role": "user", "content": "   "}]) == []


class TestFerramentas:
    def test_input_schema_vira_parameters(self):
        tools = [{"name": "ver_semana", "description": "vê a semana",
                  "input_schema": {"type": "object",
                                   "properties": {"semana_inicio": {"type": "string"}},
                                   "required": ["semana_inicio"]}}]
        decl = ia_client._converter_ferramentas(tools)[0].function_declarations[0]
        assert decl.name == "ver_semana"
        assert "semana_inicio" in decl.parameters.properties

    def test_ferramenta_sem_argumento_nao_manda_parameters(self):
        # Objeto de propriedades vazio é recusado pelo Gemini.
        tools = [{"name": "ping", "description": "ping",
                  "input_schema": {"type": "object", "properties": {}}}]
        decl = ia_client._converter_ferramentas(tools)[0].function_declarations[0]
        assert decl.parameters is None


class _Chamada:
    def __init__(self, nome, args, id_=None):
        self.name, self.args, self.id = nome, args, id_


class _Parte:
    def __init__(self, texto=None, chamada=None, pensamento=False):
        self.text, self.function_call, self.thought = texto, chamada, pensamento


class _Conteudo:
    def __init__(self, partes):
        self.parts = partes


class _Candidato:
    def __init__(self, partes, finish_reason="STOP"):
        self.content = _Conteudo(partes)
        self.finish_reason = finish_reason


class _Uso:
    def __init__(self, entrada=0, saida=0, pensamento=0, cache=0):
        self.prompt_token_count = entrada
        self.candidates_token_count = saida
        self.thoughts_token_count = pensamento
        self.cached_content_token_count = cache


class _Bruta:
    def __init__(self, partes, uso=None, finish_reason="STOP"):
        self.candidates = [_Candidato(partes, finish_reason)]
        self.usage_metadata = uso


class TestResposta:
    def test_texto_simples(self):
        r = ia_client._resposta_de(_Bruta([_Parte(texto="oi")]), "gemini-x")
        assert r.content[0].type == "text" and r.content[0].text == "oi"
        assert r.stop_reason == "end_turn"
        assert r.modelo_real == "gemini-x"

    def test_chamada_de_ferramenta_marca_stop_reason(self):
        bruta = _Bruta([_Parte(chamada=_Chamada("ver_semana", {"semana_inicio": "2026-09-14"}))])
        r = ia_client._resposta_de(bruta, "gemini-x")
        assert r.stop_reason == "tool_use"
        assert r.content[0].name == "ver_semana"
        assert r.content[0].input == {"semana_inicio": "2026-09-14"}

    def test_resumo_de_raciocinio_nao_vira_resposta(self):
        # Se o "pensando..." entrasse como texto, o json.loads de quem chamou
        # engasgaria numa prosa em vez de achar o plano.
        bruta = _Bruta([_Parte(texto="deixa eu pensar", pensamento=True),
                        _Parte(texto='{"ok": true}')])
        r = ia_client._resposta_de(bruta, "gemini-x")
        assert [b.text for b in r.content] == ['{"ok": true}']

    def test_resposta_vazia_vira_texto_vazio(self):
        # Bloqueio de segurança ou corte por teto: quem chamou espera achar
        # `.text` e cair no próprio fallback, não estourar StopIteration.
        r = ia_client._resposta_de(_Bruta([], finish_reason="SAFETY"), "gemini-x")
        assert r.content[0].type == "text" and r.content[0].text == ""

    def test_tokens_de_pensamento_contam_como_saida(self):
        bruta = _Bruta([_Parte(texto="ok")], uso=_Uso(entrada=100, saida=20, pensamento=30, cache=5))
        r = ia_client._resposta_de(bruta, "gemini-x")
        assert r.usage.input_tokens == 100
        assert r.usage.output_tokens == 50
        assert r.usage.cache_read_input_tokens == 5

    def test_assinatura_da_chamada_e_guardada_para_a_rodada_seguinte(self):
        # O Gemini 3 recusa a continuação se a "thought signature" da chamada
        # não voltar. O app só guarda id/nome/args — a parte original fica aqui.
        parte = _Parte(chamada=_Chamada("ver_semana", {}, id_="chamada_x"))
        ia_client._resposta_de(_Bruta([parte]), "gemini-x")
        assert ia_client._PARTES_DE_CHAMADA["chamada_x"] is parte


class TestProvedor:
    def test_gemini_por_padrao(self, monkeypatch):
        monkeypatch.setattr(ia_client.settings, "IA_PROVEDOR", "gemini")
        assert ia_client.usando_gemini() is True

    def test_claude_quando_pedido(self, monkeypatch):
        monkeypatch.setattr(ia_client.settings, "IA_PROVEDOR", "claude")
        assert ia_client.usando_gemini() is False

    def test_sem_escolha_prefere_quem_nao_cobra(self, monkeypatch):
        monkeypatch.setattr(ia_client.settings, "IA_PROVEDOR", "")
        monkeypatch.setattr(ia_client.settings, "GEMINI_API_KEY", "chave")
        monkeypatch.setattr(ia_client.settings, "ANTHROPIC_API_KEY", "chave-paga")
        assert ia_client.usando_gemini() is True
