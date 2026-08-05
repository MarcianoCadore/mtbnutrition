"""Cria o bloco `assinatura` para quem se cadastrou antes do paywall existir.

Antes desta migração o acesso era decidido por `telefone_verificado`, ligado à
mão pelo admin. A regra de conversão preserva o que já estava valendo — ninguém
perde acesso por causa da migração, e ninguém ganha 14 dias grátis que já tinha
usado:

    pagamento_confirmado = True   → ativa, 30 dias a partir de hoje
    telefone_verificado  = True   → ativa, 30 dias (já usava, estava liberado)
    nenhum dos dois               → trial de 14 dias (nunca chegou a usar)

Rodar uma vez, na subida da versão:

    python -m scripts.migrar_assinaturas          # simula, não grava
    python -m scripts.migrar_assinaturas --gravar
"""
import asyncio
import sys
from datetime import datetime, timedelta, timezone

from app.services.assinatura_service import CICLO_DIAS, novo_trial
from app.services.mongo_service import get_db


def _destino(u: dict) -> tuple[dict, str]:
    agora = datetime.now(timezone.utc)
    if u.get("pagamento_confirmado"):
        motivo = "pagamento confirmado"
    elif u.get("telefone_verificado"):
        motivo = "acesso liberado pelo admin"
    else:
        return novo_trial(agora), "nunca liberado → trial de 14 dias"

    return {
        "status": "ativa",
        "trial_inicio": u.get("criado_em"),
        "trial_fim": None,
        "pago_ate": agora + timedelta(days=CICLO_DIAS),
        "confirmado_em": agora,
        "avisos_enviados": [],
    }, f"{motivo} → ativa por {CICLO_DIAS} dias"


async def main(gravar: bool) -> None:
    db = get_db()
    cursor = db.users.find(
        {"assinatura": {"$exists": False}},
        {"login": 1, "nome": 1, "telefone_verificado": 1,
         "pagamento_confirmado": 1, "criado_em": 1},
    )
    usuarios = await cursor.to_list(length=None)

    if not usuarios:
        print("Nada a migrar: todos os usuários já têm assinatura.")
        return

    print(f"{len(usuarios)} usuário(s) sem bloco de assinatura:\n")
    for u in usuarios:
        bloco, motivo = _destino(u)
        fim = bloco.get("pago_ate") or bloco.get("trial_fim")
        print(f"  {u.get('login', '?'):<20} {motivo:<45} até {fim.date() if fim else '—'}")
        if gravar:
            await db.users.update_one({"_id": u["_id"]}, {"$set": {"assinatura": bloco}})

    print()
    if gravar:
        print(f"✅ {len(usuarios)} usuário(s) migrado(s).")
    else:
        print("Simulação — nada foi gravado. Rode com --gravar para aplicar.")


if __name__ == "__main__":
    asyncio.run(main("--gravar" in sys.argv))
