"""Saneia descrições de treino já gravadas e alinha o TIPO à descrição.

Dois problemas antigos que ficaram no banco (db.semanas[].treinos[]):

1) Texto poluído na descrição:
   - faixas de bpm no texto (ex.: "Zona 2 (113-132 bpm)") — a FC real vem do
     modal/legenda, por atleta;
   - cabeçalhos "TIPO — DATA" (o nome do workout do app), que o round-trip de
     sync com o Garmin prefixava e acumulava a cada envia→puxa.

2) Tipo divergente da descrição: o classificador antigo lia uma prescrição de
   VO2máx ("5×4 min Z5 | >318W") como RECUPERACAO/Z2 (contava o aquecimento e a
   soltura). Resultado: badge "Recuperação" num treino que é claramente VO2máx.
   Aqui, quando a SÉRIE PRINCIPAL é inequívoca (blocos de Z5), o tipo passa a
   SEGUIR a descrição.

NÃO reescreve o corpo da prescrição nem toca em cadência/duração/alvo do Garmin.
Idempotente. Dry-run por padrão; use --apply para gravar.

Uso:
    python scripts/limpar_bpm_descricoes.py           # dry-run (só mostra)
    python scripts/limpar_bpm_descricoes.py --apply   # grava as mudanças
"""

import asyncio
import sys
import os

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.services.mongo_service import get_db  # noqa: E402
# Mesmas funções do import do Garmin e da resposta da API:
from app.services.plano_semana_service import limpar_descricao_planejada  # noqa: E402
from app.services.ai_service import tipo_definitivo  # noqa: E402


async def main(apply: bool) -> None:
    db = get_db()
    print("=" * 60)
    print(f"Saneamento de descrições + alinhamento de tipo — "
          f"modo: {'APLICAR' if apply else 'DRY-RUN'}")
    print("=" * 60)

    total_docs = 0
    total_treinos = 0
    desc_alteradas = 0
    tipos_alterados = 0
    exemplos = 0

    async for doc in db.semanas.find({}):
        total_docs += 1
        treinos = doc.get("treinos", [])
        novos = []
        mudou_doc = False
        for t in treinos:
            total_treinos += 1
            nt = dict(t)
            mudou_treino = False

            desc = t.get("descricao")
            limpo = limpar_descricao_planejada(desc)
            if limpo != desc:
                desc_alteradas += 1
                nt["descricao"] = limpo
                mudou_treino = True

            # Tipo segue a descrição quando a série principal (Z5) é inequívoca.
            td = tipo_definitivo(nt.get("descricao"))
            if td and td != t.get("tipo"):
                tipos_alterados += 1
                nt["tipo"] = td
                mudou_treino = True

            if mudou_treino:
                mudou_doc = True
                if exemplos < 12:
                    exemplos += 1
                    print(f"\n[{doc.get('semana_inicio')} / {t.get('data')}]")
                    if nt.get("tipo") != t.get("tipo"):
                        print(f"  TIPO  : {t.get('tipo')!r} → {nt.get('tipo')!r}")
                    if nt.get("descricao") != desc:
                        print(f"  ANTES : {desc!r}")
                        print(f"  DEPOIS: {nt.get('descricao')!r}")
            novos.append(nt)

        if mudou_doc and apply:
            await db.semanas.update_one({"_id": doc["_id"]}, {"$set": {"treinos": novos}})

    print("\n" + "-" * 60)
    print(f"Semanas: {total_docs} | treinos: {total_treinos} | "
          f"descrições limpas: {desc_alteradas} | tipos corrigidos: {tipos_alterados}")
    if not apply:
        print("DRY-RUN — nada foi gravado. Rode com --apply para aplicar.")
    else:
        print("APLICADO — banco atualizado.")


if __name__ == "__main__":
    asyncio.run(main(apply="--apply" in sys.argv))
