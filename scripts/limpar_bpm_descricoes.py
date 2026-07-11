"""Remove faixas de bpm/watts JÁ GRAVADAS nas descrições de treino.

Contexto: descrições geradas pela IA antes do fix "código dono dos números"
traziam faixas de FC/watts erradas no texto (ex.: "Zona 2 (113-132 bpm)" quando
a Z2 do atleta é 132-150). O alvo real no Garmin sempre esteve correto; só o
TEXTO divergia. Novas gerações já saem sem bpm no texto — este script limpa as
descrições antigas que ficaram no banco (db.semanas[].treinos[].descricao).

NÃO toca em cadência (rpm), estrutura, tipo, duração nem no alvo do Garmin.
Idempotente. Dry-run por padrão; use --apply para gravar.

Uso:
    python scripts/limpar_bpm_descricoes.py           # dry-run (só mostra)
    python scripts/limpar_bpm_descricoes.py --apply   # grava as mudanças
"""

import asyncio
import re
import sys
import os

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.services.mongo_service import get_db  # noqa: E402

# Parênteses citando bpm: "(113-132 bpm)", "(>177 bpm)", "(<145 bpm)"
_BPM_PAREN = re.compile(r"\s*\([^)]*bpm[^)]*\)", re.IGNORECASE)
# Parênteses citando watts: "(171-231W)", "(>327 W)"
_WATTS_PAREN = re.compile(r"\s*\([^)]*\d\s*W\s*\)", re.IGNORECASE)
# Faixas soltas de bpm (com preposição opcional): "abaixo de 153 bpm", "146-158 bpm", ">177 bpm"
_BPM_BARE = re.compile(
    r"\s*(?:abaixo de |acima de |at[ée] |de )?[<>]?\s*\d{2,3}\s*[–\-a]?\s*\d{0,3}\s*bpm",
    re.IGNORECASE,
)


def limpar_descricao(txt: str | None) -> str | None:
    """Remove faixas de bpm/watts do texto, preservando o resto (cadência, zona, estrutura)."""
    if not txt:
        return txt
    t = _BPM_PAREN.sub("", txt)
    t = _WATTS_PAREN.sub("", t)
    t = _BPM_BARE.sub("", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"\s+([.,;:])", r"\1", t)          # remove espaço antes de pontuação
    t = re.sub(r"\(\s*\)", "", t)                  # parênteses vazios residuais
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


async def main(apply: bool) -> None:
    db = get_db()
    print("=" * 60)
    print(f"Limpeza de bpm/watts nas descrições — modo: {'APLICAR' if apply else 'DRY-RUN'}")
    print("=" * 60)

    total_docs = 0
    total_treinos = 0
    total_alterados = 0
    exemplos = 0

    async for doc in db.semanas.find({}):
        total_docs += 1
        treinos = doc.get("treinos", [])
        novos = []
        mudou_doc = False
        for t in treinos:
            total_treinos += 1
            desc = t.get("descricao")
            limpo = limpar_descricao(desc)
            if limpo != desc:
                total_alterados += 1
                mudou_doc = True
                if exemplos < 8:
                    exemplos += 1
                    print(f"\n[{doc.get('semana_inicio')} / {t.get('data')}]")
                    print(f"  ANTES : {desc!r}")
                    print(f"  DEPOIS: {limpo!r}")
                nt = dict(t)
                nt["descricao"] = limpo
                novos.append(nt)
            else:
                novos.append(t)

        if mudou_doc and apply:
            await db.semanas.update_one({"_id": doc["_id"]}, {"$set": {"treinos": novos}})

    print("\n" + "-" * 60)
    print(f"Semanas: {total_docs} | treinos: {total_treinos} | descrições alteradas: {total_alterados}")
    if not apply:
        print("DRY-RUN — nada foi gravado. Rode com --apply para aplicar.")
    else:
        print("APLICADO — descrições atualizadas no banco.")


if __name__ == "__main__":
    asyncio.run(main(apply="--apply" in sys.argv))
