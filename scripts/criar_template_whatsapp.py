"""
Cria o template "passthrough" de WhatsApp no Twilio (Content API) e o submete
para aprovação da Meta. Depois de aprovado, copie o SID (HX...) impresso para
a variável TWILIO_CONTENT_SID no .env.

O template tem uma única variável {{1}} que carrega a mensagem inteira já
formatada pelo bot — assim plano diário, lembretes e pós-treino reutilizam o
mesmo template (uma só aprovação).

Uso:
    python -m scripts.criar_template_whatsapp          # cria + submete aprovação
    python -m scripts.criar_template_whatsapp status   # consulta status da aprovação
"""
import sys
import json
import httpx

from config.settings import settings

CONTENT_API = "https://content.twilio.com/v1/Content"
TEMPLATE_NAME = "mtb_notificacao"      # minúsculas, alfanumérico + underscore
LANGUAGE = "pt_BR"
# Texto fixo + variável. O texto fixo é exigido pela Meta (não aprova só {{1}}).
BODY = "🚵 *MTB Nutrition*\n\n{{1}}"


def _auth() -> tuple[str, str]:
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        sys.exit("❌ Configure TWILIO_ACCOUNT_SID e TWILIO_AUTH_TOKEN no .env")
    return settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN


def criar() -> str:
    auth = _auth()
    payload = {
        "friendly_name": TEMPLATE_NAME,
        "language": LANGUAGE,
        "variables": {"1": "Exemplo de mensagem do bot."},
        "types": {
            "twilio/text": {"body": BODY},
        },
    }
    r = httpx.post(CONTENT_API, auth=auth, json=payload, timeout=30)
    if r.status_code >= 300:
        sys.exit(f"❌ Erro ao criar conteúdo ({r.status_code}): {r.text}")
    sid = r.json()["sid"]
    print(f"✅ Conteúdo criado: {sid}")
    return sid


def submeter_aprovacao(sid: str) -> None:
    auth = _auth()
    url = f"{CONTENT_API}/{sid}/ApprovalRequests/whatsapp"
    payload = {"name": TEMPLATE_NAME, "category": "UTILITY"}
    r = httpx.post(url, auth=auth, json=payload, timeout=30)
    if r.status_code >= 300:
        sys.exit(f"❌ Erro ao submeter aprovação ({r.status_code}): {r.text}")
    print("✅ Submetido para aprovação da Meta (categoria UTILITY).")
    print(f"\n👉 Cole no .env quando aprovado:\n   TWILIO_CONTENT_SID={sid}\n")
    print("   A aprovação costuma levar de alguns minutos a algumas horas.")
    print("   Acompanhe com: python -m scripts.criar_template_whatsapp status")


def status() -> None:
    auth = _auth()
    if not settings.TWILIO_CONTENT_SID:
        # lista todos os contents para localizar o template criado
        r = httpx.get(CONTENT_API, auth=auth, timeout=30)
        encontrados = [
            c for c in r.json().get("contents", [])
            if c.get("friendly_name") == TEMPLATE_NAME
        ]
        if not encontrados:
            sys.exit("Nenhum template encontrado. Rode sem argumentos para criar.")
        sid = encontrados[0]["sid"]
        print(f"(TWILIO_CONTENT_SID não setado — usando {sid} encontrado pelo nome)")
    else:
        sid = settings.TWILIO_CONTENT_SID

    url = f"{CONTENT_API}/{sid}/ApprovalRequests"
    r = httpx.get(url, auth=auth, timeout=30)
    if r.status_code >= 300:
        sys.exit(f"❌ Erro ao consultar status ({r.status_code}): {r.text}")
    print(json.dumps(r.json(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        status()
    else:
        sid = criar()
        submeter_aprovacao(sid)
