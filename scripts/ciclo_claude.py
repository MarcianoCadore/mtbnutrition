#!/usr/bin/env python3
"""Abre e fecha o ciclo de 90 dias do atleta, com o Claude Code no terminal.

Irmão de semana_claude.py, e pela mesma razão: o trabalho em que a qualidade do
raciocínio mais importa é o que roda com menos frequência. A semana sai toda
segunda; o ciclo sai quatro vezes por ano. É o lugar óbvio para pôr o modelo
que pensa melhor, sem pagar API.

A divisão de trabalho é a de sempre — código dono dos números, treinador dono
do julgamento:

    `diagnostico` levanta a foto do atleta (FTP, W/kg, curva de potência, carga
    crônica, aderência, provas na janela) e JÁ MONTA o esqueleto de blocos.
    Nada disso é opinião: é `ciclo_service.esqueleto_blocos`, determinístico.

    Você lê isso e escreve a parte que exige treinador: os limitadores (o que
    segura o atleta, com a evidência), o objetivo do ciclo, as metas mensuráveis,
    o objetivo de cada bloco e o racional.

    `salvar` costura os dois e grava. O esqueleto é recalculado na hora da
    gravação, não vem do JSON: assim não há como um ciclo entrar no banco com
    um bloco sem semana de descarga.

Roda no servidor, onde ficam o .env e a senha do Atlas:

    ssh ubuntu@<vm> "cd /opt/mtbnutrition && sudo -u mtbnutri venv/bin/python \\
        scripts/ciclo_claude.py diagnostico"
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
os.chdir(RAIZ)

from app.services import ciclo_service as cs  # noqa: E402
from app.services.mongo_service import get_db  # noqa: E402
from app.services.user_service import get_por_id  # noqa: E402

# Dono do app. Mexer no ciclo de outro atleta exige --user-id explícito: um erro
# aqui reescreveria 90 dias de treino de alguém.
USER_PADRAO = os.environ.get("SEMANA_USER_ID", "6a2ec0cf191f3f1a12547e21")


def _proxima_segunda() -> str:
    """Segunda que vem — um ciclo nunca começa no meio de uma semana."""
    hoje = date.today()
    return (hoje + timedelta(days=(7 - hoje.weekday()) % 7 or 7)).isoformat()


def _sem_cerca(texto: str) -> str:
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


# ─── Diagnóstico: a foto de abertura ─────────────────────────────────────────

async def _levantar(user_id: str, inicio: str) -> dict:
    """Tudo o que o treinador precisa saber antes de desenhar 90 dias."""
    from app.services.config_service import get_zonas_potencia
    from app.services.evolucao_service import resumo_semanal
    from app.services.fisiologia_service import _coletar_historico, calcular_metricas
    from app.services.prova_service import listar_provas

    u = await _atleta(user_id)
    perfil = u.get("perfil") or {}
    db = get_db()

    zp = await get_zonas_potencia(user_id)
    ftp = (zp or {}).get("ftp")
    peso = float(perfil.get("peso_kg") or 0) or None

    # 12 semanas de volume/carga/aderência. É a janela da tela de evolução — e
    # é a primeira vez que ela entra numa DECISÃO, não só num gráfico.
    semanal = await resumo_semanal(user_id, semanas=12)

    # Duas leituras de carga, de propósito e para perguntas diferentes:
    #   `metricas` é a do parecer semanal (4 semanas) — "como ele está AGORA";
    #   `carga_ref` é a do ciclo (12 semanas, mediana) — "quanto ele sustenta".
    # Herdar a de 4 semanas aqui é o que fazia o ciclo abrir um bloco de base
    # acima do maior pico histórico do atleta.
    metricas = calcular_metricas(await _coletar_historico(user_id, cs.segunda_de(inicio)))
    # A meta de horas do perfil entra no cálculo: o ciclo mira onde o atleta
    # quer chegar, em rampa, e não só onde ele esteve.
    from app.services.plano_semana_service import volume_semanal_do_usuario
    volume_alvo = volume_semanal_do_usuario(u.get("preferencias"))
    carga_ref = cs.carga_de_referencia(semanal, volume_alvo)

    curva = await db.curva_potencia.find_one({"user_id": user_id},
                                             sort=[("atualizado_em", -1)])
    ftp_hist = [
        {"data": f.get("data"), "ftp": f.get("ftp"), "origem": f.get("origem")}
        async for f in db.ftp_historico.find({"user_id": user_id}).sort("data", 1)
    ]

    fim = cs.fim_do_ciclo(inicio)
    provas = [p for p in await listar_provas(user_id) if p.get("data") and p["data"] >= inicio]
    na_janela = [p for p in provas if p["data"] <= fim]

    return {
        "atleta": u, "perfil": perfil, "inicio": inicio, "fim": fim,
        "ftp": ftp, "peso": peso,
        "w_kg": round(ftp / peso, 2) if ftp and peso else None,
        "semanal": semanal, "metricas": metricas, "carga_ref": carga_ref,
        "volume_alvo": volume_alvo,
        "curva": (curva or {}).get("curva") or (curva or {}).get("pontos"),
        "ftp_hist": ftp_hist,
        "provas_janela": na_janela,
        "provas_depois": [p for p in provas if p["data"] > fim][:3],
        # O esqueleto enxerga também as provas RECÉM-CORRIDAS: uma prova A na
        # semana anterior faz o ciclo abrir em transição, não em carga.
        "blocos": cs.esqueleto_blocos(
            inicio,
            na_janela + await _provas_recentes(user_id, inicio),
            carga_ref,
        ),
    }


async def _provas_recentes(user_id: str, inicio: str) -> list[dict]:
    from app.services.prova_service import listar_provas

    limite = (datetime.strptime(inicio, "%Y-%m-%d").date()
              - timedelta(weeks=cs.SEMANAS_RESIDUO_PROVA)).isoformat()
    return [p for p in await listar_provas(user_id)
            if p.get("data") and limite <= p["data"] < inicio]


def _imprimir_diagnostico(d: dict) -> None:
    u, m = d["atleta"], d["metricas"]
    perfil = d["perfil"]
    print(f"### CICLO DE 90 DIAS — {u.get('nome')} | {d['inicio']} a {d['fim']}")
    print()
    print("## ONDE O ATLETA ESTÁ")
    print(f"  {perfil.get('idade')} anos, {perfil.get('peso_kg')} kg, "
          f"objetivo: {(u.get('preferencias') or {}).get('objetivo')}")
    print(f"  FTP: {d['ftp'] or '—'} W" + (f" ({d['w_kg']} W/kg)" if d["w_kg"] else ""))
    if d["ftp_hist"]:
        print("  Histórico de FTP: " +
              " → ".join(f"{f['data']} {f['ftp']}W ({f['origem']})" for f in d["ftp_hist"]))
    if d["curva"]:
        print(f"  Curva de potência (90d): {json.dumps(d['curva'], default=str)}")
    else:
        print("  Curva de potência: ainda sem dados — não há com que comparar o antes/depois.")
    from app.services.plano_semana_service import formatar_horas
    alvo_txt = (f" (meta do perfil: {formatar_horas(d['volume_alvo'])}/sem, em rampa)"
                if d["volume_alvo"] else "")
    print(f"  Carga de referência do ciclo: {d['carga_ref'] or '—'} TSS/sem"
          f"{alvo_txt}  ← é ela que ancora os alvos abaixo")
    print(f"  Carga das últimas 4 semanas (parecer): {m.get('carga_cronica') or '—'} TSS/sem | "
          f"aguda: {m.get('carga_aguda') or '—'} | ACWR: {m.get('acwr') or '—'}")
    print(f"  Aderência ao plano: {m.get('aderencia_pct') or '—'}%")
    if m.get("furos_por_dia"):
        print(f"  Furos por dia da semana: {m['furos_por_dia']}")

    print()
    print("## 12 SEMANAS (volume, carga, aderência)")
    for s in d["semanal"]:
        print(f"  {s['semana']}  {s.get('minutos',0):>5} min | TSS {s.get('tss',0):>4} | "
              f"{s.get('sessoes',0)}/{s.get('planejados',0)} sessões | {s.get('km',0):>6} km")

    print()
    print("## PROVAS")
    if d["provas_janela"]:
        for p in d["provas_janela"]:
            print(f"  DENTRO do ciclo: {p['data']} [{p.get('prioridade')}] {p['nome']} — "
                  f"{p.get('distancia_km')}km {p.get('altimetria_m')}m {p.get('terreno')}")
    else:
        print("  Nenhuma prova nas 13 semanas — o ciclo é de DESENVOLVIMENTO.")
    for p in d["provas_depois"]:
        print(f"  depois do ciclo: {p['data']} [{p.get('prioridade')}] {p['nome']}")

    print()
    print("## ESQUELETO JÁ MONTADO PELO CÓDIGO (não é negociável — só o conteúdo é seu)")
    for b in d["blocos"]:
        print(f"  Bloco {b['n']} — {cs.FOCO_LABEL.get(b['foco'], b['foco'])} "
              f"| {b['inicio']} a {b['fim']} ({b['semanas']} semanas)")
        for det in b["semanas_detalhe"]:
            alvo = f"{det['alvo_tss']} TSS" if det["alvo_tss"] else "sem alvo (falta carga crônica)"
            print(f"       {det['semana']}  {det['papel']:<10} {alvo}")

    print()
    print("""## O QUE VOCÊ ESCREVE (responda SÓ com este JSON)

{
  "objetivo": "uma frase: o que estes 90 dias entregam",
  "limitadores": [
    {"nome": "curto e concreto",
     "evidencia": "o dado que prova — cite números das semanas acima",
     "como_atacar": "o que a prescrição deve fazer, em termos que o gerador de semana consiga seguir",
     "bloco_alvo": 1}
  ],
  "metas": [
    {"chave": "ftp", "descricao": "FTP", "de": 300, "para": 320, "unidade": "W",
     "aferir_em": "2026-12-14"}
  ],
  "objetivos_blocos": {"1": "objetivo do bloco 1", "2": "...", "3": "..."},
  "racional": "por que o ciclo é assim — 2 a 4 frases, na voz de treinador falando com o atleta"
}

REGRAS:
- Limitador sem evidência numérica não é limitador, é palpite. Cite o dado.
- `como_atacar` é lido pelo gerador da semana toda segunda: escreva instrução
  executável ("teto de 165 W nos dias de recuperação"), não conselho vago
  ("treinar mais leve").
- `bloco_alvo` é o número do bloco (ou null para valer no ciclo inteiro).
- Metas precisam ser aferíveis com o que o app mede: FTP, curva de potência,
  TSS, aderência, cadência. Nada que dependa de sensação.""")


async def cmd_diagnostico(args):
    _imprimir_diagnostico(await _levantar(args.user_id, args.inicio))


# ─── Salvar ──────────────────────────────────────────────────────────────────

async def cmd_salvar(args):
    escrito = _carregar_json(args.arquivo)
    d = await _levantar(args.user_id, args.inicio)
    u = d["atleta"]

    if not escrito.get("objetivo"):
        raise SystemExit("❌ o ciclo precisa de um `objetivo` — sem ele é só uma grade vazia.")

    # O esqueleto NÃO vem do JSON: é recalculado aqui. Se viesse do modelo, um
    # ciclo poderia entrar no banco com um bloco de 8 semanas sem descarga — o
    # defeito exato que este ciclo existe para eliminar.
    blocos = d["blocos"]
    objetivos = {str(k): v for k, v in (escrito.get("objetivos_blocos") or {}).items()}
    for b in blocos:
        b["objetivo"] = objetivos.get(str(b["n"]))

    m = d["metricas"]
    ciclo = {
        "numero": await cs.proximo_numero(args.user_id),
        "inicio": d["inicio"],
        "fim": d["fim"],
        "diagnostico": {
            "ftp": d["ftp"], "peso_kg": d["peso"], "w_kg": d["w_kg"],
            "carga_cronica": m.get("carga_cronica"),
            "aderencia_pct": m.get("aderencia_pct"),
            "volume_semanal_min": round(
                sum(s.get("minutos", 0) for s in d["semanal"]) / max(len(d["semanal"]), 1)),
            "curva_potencia": d["curva"],
            "gerado_em": datetime.now(timezone.utc).isoformat(),
        },
        "limitadores": escrito.get("limitadores") or [],
        "objetivo": escrito["objetivo"],
        "metas": escrito.get("metas") or [],
        # A prova-alvo do ciclo é a de maior prioridade, não a mais próxima:
        # numa temporada com quatro largadas a primeira raramente é a que manda.
        "prova_alvo": (
            {k: sorted(d["provas_janela"],
                       key=lambda p: ({"A": 0, "B": 1, "C": 2}.get(p.get("prioridade"), 3),
                                      p["data"]))[0].get(k)
             for k in ("nome", "data", "prioridade")}
            if d["provas_janela"] else None
        ),
        "blocos": blocos,
        "racional": escrito.get("racional") or "",
        "criado_por": "claude-code",
    }

    if args.simular:
        print(f"(simulação — nada gravado) ciclo {ciclo['numero']} de {u.get('nome')}")
    else:
        await cs.salvar_ciclo(args.user_id, ciclo)
        print(f"✅ ciclo {ciclo['numero']} salvo para {u.get('nome')} "
              f"({ciclo['inicio']} a {ciclo['fim']})")

    print(f"\n🎯 {ciclo['objetivo']}")
    if ciclo["racional"]:
        print(f"   {ciclo['racional']}")
    for l in ciclo["limitadores"]:
        alvo = f"bloco {l['bloco_alvo']}" if l.get("bloco_alvo") else "ciclo todo"
        print(f"🔒 {l.get('nome')} ({alvo}) → {l.get('como_atacar')}")
    for meta in ciclo["metas"]:
        print(f"📈 {meta.get('descricao') or meta.get('chave')}: "
              f"{meta.get('de')} → {meta.get('para')} {meta.get('unidade') or ''}")
    for b in blocos:
        print(f"   Bloco {b['n']} {cs.FOCO_LABEL.get(b['foco'], b['foco']):<26} "
              f"{b['inicio']}..{b['fim']}  {b.get('objetivo') or ''}")


# ─── Consulta ────────────────────────────────────────────────────────────────

async def cmd_ver(args):
    ciclo = await cs.ciclo_ativo(args.user_id)
    if not ciclo:
        print("Nenhum ciclo ativo. Rode `diagnostico` e depois `salvar`.")
        return
    hoje = date.today().isoformat()
    pos = cs.posicao(ciclo, cs.segunda_de(hoje))
    print(f"Ciclo {ciclo['numero']}: {ciclo['inicio']} a {ciclo['fim']}")
    print(f"🎯 {ciclo.get('objetivo')}")
    if pos:
        print(f"📍 semana {pos['semana_no_ciclo']}/{cs.SEMANAS_CICLO} | "
              f"bloco {pos['n_bloco']} ({pos['bloco']['foco']}) | "
              f"semana {pos['semana_no_bloco']}/{pos['semanas_no_bloco']} do bloco | "
              f"papel: {pos['papel']} | alvo {pos['alvo_tss']} TSS")
    print()
    print(cs.bloco_prompt(ciclo, cs.segunda_de(hoje)))


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--user-id", default=USER_PADRAO)
    p.add_argument("--inicio", default=_proxima_segunda(),
                   help="Segunda-feira em que o ciclo começa (padrão: a próxima).")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("diagnostico", help="Foto do atleta + esqueleto dos 90 dias")
    sp = sub.add_parser("salvar", help="Salva o ciclo escrito pelo treinador (JSON)")
    sp.add_argument("--arquivo", default="-", help="Arquivo JSON ou - para stdin")
    sp.add_argument("--simular", action="store_true", help="Não grava, só mostra")
    sub.add_parser("ver", help="Mostra o ciclo ativo e onde o atleta está nele")

    args = p.parse_args()
    asyncio.run({
        "diagnostico": cmd_diagnostico,
        "salvar": cmd_salvar,
        "ver": cmd_ver,
    }[args.cmd](args))


if __name__ == "__main__":
    main()
