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
