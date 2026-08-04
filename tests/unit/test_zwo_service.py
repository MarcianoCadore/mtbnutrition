"""Gerador de .zwo (app.services.zwo_service.build_zwo_xml).

Contrato do formato Zwift Workout: root <workout_file>, potências como FRAÇÃO do
FTP (relativo — não exige FTP salvo), blocos Warmup/SteadyState/Cooldown e
mensagens como <textevent> aninhado.
"""
import xml.etree.ElementTree as ET

from app.services.zwo_service import build_zwo_xml


def _root(tipo="TIROS", dur=62, **kw):
    xml = build_zwo_xml(tipo, dur, **kw)
    return ET.fromstring(xml), xml


def test_estrutura_zwift_basica():
    root, xml = _root()
    assert root.tag == "workout_file"
    assert root.find("sportType").text == "bike"
    assert root.find("author").text == "IA Performance"
    assert root.find("workout") is not None
    assert xml.startswith("<?xml")


def test_potencias_sao_fracao_do_ftp():
    root, _ = _root("VO2MAX", 62)
    w = root.find("workout")
    for el in w:
        for attr in ("Power", "PowerLow", "PowerHigh"):
            v = el.get(attr)
            if v is not None:
                assert 0.0 <= float(v) <= 2.0, (el.tag, attr, v)  # 1.0 = FTP


def test_blocos_usam_tags_validas_do_zwift():
    root, _ = _root("TIROS", 62)
    tags = {el.tag for el in root.find("workout")}
    assert tags <= {"Warmup", "Cooldown", "SteadyState", "IntervalsT", "Ramp", "FreeRide"}
    assert "Warmup" in tags and "SteadyState" in tags


def test_warmup_e_cooldown_sao_rampas():
    root, _ = _root("VO2MAX", 62)
    blocos = list(root.find("workout"))
    assert blocos[0].tag == "Warmup"
    assert blocos[-1].tag == "Cooldown"
    for b in (blocos[0], blocos[-1]):
        assert b.get("PowerLow") is not None and b.get("PowerHigh") is not None


def test_esforco_z5_fica_acima_do_ftp():
    root, _ = _root("TIROS", 62)
    sprint = next(b for b in root.find("workout")
                  if b.tag == "SteadyState" and int(b.get("Duration")) == 30)
    assert float(sprint.get("Power")) > 1.0  # Z5 = 106-120% FTP


def test_textevents_de_antecipacao():
    root, _ = _root("TIROS", 62)
    eventos = [t for b in root.find("workout") for t in b.findall("textevent")]
    assert eventos, "deveria haver mensagens"
    # Todos com timeoffset numérico >= 0 (Zwift exibe no tempo relativo ao bloco).
    assert all(int(t.get("timeoffset")) >= 0 for t in eventos)
    assert any("15s" in (t.get("message") or "") for t in eventos)
    assert any("conclu" in (t.get("message") or "").lower() for t in eventos)


def _potencias(bloco) -> list[float]:
    """Todas as potências do bloco (rampa devolve início e fim)."""
    if bloco.tag in ("Warmup", "Cooldown"):
        return [float(bloco.get("PowerLow")), float(bloco.get("PowerHigh"))]
    return [float(bloco.get("Power"))]


def test_recuperacao_nao_tem_pico_nas_pontas():
    """Regressão: as rampas iam até o topo da Z1 (55% FTP) e o miolo ficava no meio
    da banda (27,5%) — o treino de recuperação saía pico/queda/pico no rolo."""
    root, _ = _root("RECUPERACAO", 61)
    blocos = list(root.find("workout"))
    miolo = float(next(b for b in blocos if b.tag == "SteadyState").get("Power"))
    for b in blocos:
        for p in _potencias(b):
            assert p <= miolo + 1e-9, (b.tag, p, miolo)  # nada acima do bloco principal


def test_recuperacao_fica_perto_de_50pct_do_ftp():
    """27% do FTP é pedalar à toa; recuperação ativa vive na casa dos 45-55%."""
    root, _ = _root("RECUPERACAO", 61)
    for b in root.find("workout"):
        for p in _potencias(b):
            assert 0.40 <= p <= 0.60, (b.tag, p)


def test_cooldown_comeca_mais_forte_do_que_termina():
    """Zwift/MyWhoosh leem PowerLow como INÍCIO da rampa: se o menor valor vier
    primeiro, a volta à calma SOBE no fim do treino."""
    for tipo in ("RECUPERACAO", "Z2_LONGO", "TEMPO", "FORCA", "TIROS", "VO2MAX", "TESTE_FTP"):
        root, _ = _root(tipo, 62)
        cd = list(root.find("workout"))[-1]
        assert cd.tag == "Cooldown", tipo
        assert float(cd.get("PowerLow")) > float(cd.get("PowerHigh")), tipo


def test_warmup_nao_ultrapassa_o_bloco_seguinte_da_mesma_zona():
    """O aquecimento termina exatamente no valor do bloco fixo da zona — sem degrau."""
    root, _ = _root("RECUPERACAO", 61)
    blocos = list(root.find("workout"))
    assert float(blocos[0].get("PowerHigh")) == float(blocos[1].get("Power"))


def test_tipo_sem_builder_retorna_none():
    assert build_zwo_xml("NAO_EXISTE", 60) is None


def test_todos_os_tipos_geram_zwo_valido():
    for tipo in ("RECUPERACAO", "Z2_LONGO", "TEMPO", "FORCA", "TIROS", "VO2MAX", "TESTE_FTP"):
        xml = build_zwo_xml(tipo, 60)
        assert xml is not None, tipo
        ET.fromstring(xml)


def test_nome_e_descricao_escapados():
    xml = build_zwo_xml("TIROS", 62, nome="A & B <c>", descricao="x < y & z")
    root = ET.fromstring(xml)
    assert root.find("name").text == "A & B <c>"
    assert root.find("description").text == "x < y & z"
