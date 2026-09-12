#!/usr/bin/env python3
"""Gera a próxima semana de treinos com o Claude Code, sem API paga.

A conta da Anthropic ficou sem crédito e o dono do app não quer pagar API. Mas
ele já paga o Claude Code — então o modelo que monta a semana passa a ser o do
terminal, e não uma chamada cobrada. Este script é a ponte:

    1. `parecer-prompt` / `parecer-salvar` → o parecer fisiológico das últimas
       semanas (o mesmo prompt que ia para o Opus).
    2. `prompt`  → imprime o prompt da próxima semana, já com o parecer dentro.
    3. `salvar`  → recebe o JSON gerado, passa pelas MESMAS validações do app
       (tipos, teto de duração, regras de agenda, fase da prova, taper, legenda
       de zonas, potenciômetro) e grava em `semanas`.

O passo 3 é o que importa: nada entra no banco cru. Quem gera muda, as travas
que protegem o atleta não.

Roda no servidor, onde ficam o .env e a senha do Atlas:

    ssh ubuntu@<vm> "sudo -u mtbnutri /opt/mtbnutrition/venv/bin/python \\
        /opt/mtbnutrition/scripts/semana_claude.py prompt"
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
# `config.settings` lê o .env pelo caminho relativo — sem entrar na raiz do
# app, rodar o script de outro diretório estoura antes de qualquer coisa.
os.chdir(RAIZ)

from app.services.mongo_service import get_db  # noqa: E402
from app.services.user_service import get_por_id  # noqa: E402

# Dono do app. Mexer no calendário de outro atleta exige --user-id explícito:
# um erro aqui reescreveria a semana de treino de alguém.
USER_PADRAO = os.environ.get("SEMANA_USER_ID", "6a2ec0cf191f3f1a12547e21")


def _segunda_desta_semana() -> str:
    hoje = date.today()
    return (hoje - timedelta(days=hoje.weekday())).isoformat()


def _sem_cerca(texto: str) -> str:
    """Tira a cerca ```json que o modelo às vezes põe em volta do JSON."""
    t = texto.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    return t.strip()


def _carregar_json(caminho: str) -> dict:
    bruto = sys.stdin.read() if caminho == "-" else Path(caminho).read_text()
    return json.loads(_sem_cerca(bruto))


async def _atleta(user_id: str) -> dict:
    u = await get_por_id(user_id)
    if not u:
        raise SystemExit(f"Usuário {user_id} não existe no banco.")
    return u


# ─── Parecer fisiológico ─────────────────────────────────────────────────────

async def cmd_parecer_prompt(args):
    from app.services.fisiologia_service import (
        _coletar_historico, _montar_prompt, calcular_metricas,
    )
    from app.services.config_service import get_zonas_potencia

    u = await _atleta(args.user_id)
    perfil = u.get("perfil") or {}
    zonas = u.get("zonas") or {}
    try:
        zp = await get_zonas_potencia(args.user_id)
        ftp = zp["ftp"] if zp else None
    except Exception:
        ftp = None

    historico = await _coletar_historico(args.user_id, args.semana)
    metricas = calcular_metricas(historico)
    atleta = {
        "nome":     u.get("nome") or "Atleta",
        "idade":    int(perfil.get("idade") or 34),
        "peso":     float(perfil.get("peso_kg") or 85),
        "objetivo": (u.get("preferencias") or {}).get("objetivo") or "performance",
        "fc_max":   int(zonas.get("fc_max") or perfil.get("fc_max") or 190),
        "limiar":   zonas.get("limiar") or perfil.get("limiar_bpm"),
        "ftp":      ftp,
    }
    print(f"### ATLETA: {atleta['nome']} | semana de referência: {args.semana}")
    print("### PROMPT DO PARECER (responda só com o JSON pedido)")
    print(_montar_prompt(atleta, historico, metricas))


async def cmd_parecer_salvar(args):
    from datetime import datetime, timezone
    from app.services.fisiologia_service import _coletar_historico, calcular_metricas

    parecer_ia = _carregar_json(args.arquivo)
    historico = await _coletar_historico(args.user_id, args.semana)
    metricas = calcular_metricas(historico)

    parecer = {
        "user_id":    args.user_id,
        "semana_ref": args.semana,
        "gerado_em":  datetime.now(timezone.utc).isoformat(),
        # Marca de origem: o parecer veio do terminal, não da API.
        "modelo":     "claude-code",
        "metricas":   metricas,
        **{k: parecer_ia.get(k) for k in
           ("estado_forma", "nivel_fadiga", "ajuste_carga",
            "pontos_atencao", "recomendacoes")},
    }
    await get_db().pareceres_fisiologicos.replace_one(
        {"user_id": args.user_id, "semana_ref": args.semana}, parecer, upsert=True)
    print(f"✅ parecer salvo | estado: {parecer.get('estado_forma')} | "
          f"fadiga: {parecer.get('nivel_fadiga')} | carga: {parecer.get('ajuste_carga')}")


# ─── Semana ──────────────────────────────────────────────────────────────────

async def _contexto(user_id: str, semana: str):
    """Contexto da próxima semana, reusando o parecer já salvo se houver."""
    from app.services.plano_semana_service import montar_contexto_semana

    parecer = await get_db().pareceres_fisiologicos.find_one(
        {"user_id": user_id, "semana_ref": semana})
    # Parecer determinístico é o que sobra quando a IA falhou — reaproveitá-lo
    # aqui seria gerar a semana às cegas justamente no passo em que dá para
    # pensar de verdade. Sem parecer bom, o prompt sai sem bloco de parecer.
    if parecer and parecer.get("modelo") == "deterministico":
        parecer = None
    if parecer:
        parecer.pop("_id", None)
    return await montar_contexto_semana(user_id, semana, parecer_pronto=parecer)


async def cmd_prompt(args):
    u = await _atleta(args.user_id)
    ctx = await _contexto(args.user_id, args.semana)
    origem = (ctx["parecer"] or {}).get("modelo", "nenhum")
    print(f"### ATLETA: {u.get('nome')} | semana base: {args.semana} "
          f"→ gerando: {ctx['proxima']} | parecer: {origem}")
    print("### SISTEMA")
    print(ctx["sistema"])
    print("### PROMPT (responda só com o JSON do plano)")
    print(ctx["prompt"])


async def cmd_salvar(args):
    from app.services.plano_semana_service import normalizar_plano

    bruto = _carregar_json(args.arquivo)
    u = await _atleta(args.user_id)
    ctx = await _contexto(args.user_id, args.semana)
    plano = normalizar_plano(bruto, ctx, modelo_usado="claude-code")
    proxima = plano["semana_proxima"]

    db = get_db()
    existente = await db.semanas.find_one(
        {"semana_inicio": proxima, "user_id": args.user_id})

    # Semana que já aconteceu não se reescreve: o plano dela virou histórico e é
    # contra ele que os treinos foram avaliados.
    if existente and any(t.get("resultado") for t in existente.get("treinos", [])):
        raise SystemExit(
            f"❌ {proxima} já tem treino com resultado registrado — não vou sobrescrever.")

    extras = [t for t in (existente or {}).get("treinos", []) if t.get("origem") == "extra"]
    doc = {
        "semana_inicio": proxima,
        "user_id": args.user_id,
        "objetivo": plano.get("progressao", ""),
        "treinos": plano["treinos"] + extras,
        "gerada_por_ia": True,
    }
    if args.simular:
        print(f"(simulação — nada gravado) {u.get('nome')} | {proxima}")
    else:
        await db.semanas.replace_one(
            {"semana_inicio": proxima, "user_id": args.user_id}, doc, upsert=True)
        print(f"✅ semana {proxima} salva para {u.get('nome')}"
              f"{' (+%d extra)' % len(extras) if extras else ''}")

    print(f"📊 {plano.get('analise_semana','')}")
    print(f"⬆️  {plano.get('progressao','')}")
    for t in plano["treinos"]:
        dur = f"{t['duracao_min']}min" if t.get("duracao_min") else "—"
        ac = " +ACADEMIA" if t.get("academia") else ""
        print(f"   {t['data']}  {t['tipo']:<12} {dur:>7}{ac}  {(t.get('descricao') or '')[:70]}")
    print("\nNão enviei nada ao Garmin — isso continua sendo um clique seu no portal.")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--user-id", default=USER_PADRAO)
    p.add_argument("--semana", default=_segunda_desta_semana(),
                   help="Segunda-feira da semana BASE (a atual). O plano gerado é o da seguinte.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("parecer-prompt", help="Imprime o prompt do parecer fisiológico")
    sp = sub.add_parser("parecer-salvar", help="Salva o parecer gerado (JSON)")
    sp.add_argument("--arquivo", default="-", help="Arquivo JSON ou - para stdin")

    sub.add_parser("prompt", help="Imprime o prompt da próxima semana")
    ss = sub.add_parser("salvar", help="Valida e salva o plano gerado (JSON)")
    ss.add_argument("--arquivo", default="-", help="Arquivo JSON ou - para stdin")
    ss.add_argument("--simular", action="store_true", help="Mostra o resultado sem gravar")

    args = p.parse_args()
    comandos = {
        "parecer-prompt": cmd_parecer_prompt,
        "parecer-salvar": cmd_parecer_salvar,
        "prompt": cmd_prompt,
        "salvar": cmd_salvar,
    }
    asyncio.run(comandos[args.cmd](args))


if __name__ == "__main__":
    main()
