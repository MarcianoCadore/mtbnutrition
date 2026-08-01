"""Gerador de XML ERG (app.services.erg_service.build_erg_xml).

Cobre o contrato do formato: XML bem-formado, blocos de potência (`WorkoutSteps`)
SEPARADOS dos eventos (`Events`), watts dentro das zonas do atleta, e a
antecipação das mensagens — o cliente lê os eventos para avisar N s antes.
"""
import xml.etree.ElementTree as ET

import pytest

from app.services.config_service import calc_zonas_potencia
from app.services.erg_service import build_erg_xml

FTP = 250


def _zonas_watts(ftp=FTP):
    return {z["zona"]: {"min": z["min"], "max": z["max"], "nome": z["nome"]}
            for z in calc_zonas_potencia(ftp)}


def _root(tipo="TIROS", dur=62, **kw):
    xml = build_erg_xml(tipo, dur, zonas_watts=_zonas_watts(), ftp=FTP, **kw)
    return ET.fromstring(xml), xml


def test_xml_bem_formado_e_estrutura_basica():
    root, xml = _root()
    assert root.tag == "Workout"
    assert root.get("version") == "1.1"
    assert root.find("Metadata/Author").text == "IA Performance"
    assert root.find("Metadata/Ftp").text == str(FTP)
    assert root.find("WorkoutSteps") is not None
    assert root.find("Events") is not None
    assert xml.startswith("<?xml")


def test_eventos_desacoplados_apontam_para_steps_existentes():
    root, _ = _root()
    steps = root.find("WorkoutSteps")
    events = root.find("Events")
    step_ids = {s.get("Id") for s in steps}
    assert len(steps) > 0 and len(events) > 0
    # Todo evento referencia um StepId válido — o cliente resolve sem olhar a árvore.
    assert all(e.get("StepId") in step_ids for e in events)


def test_cada_step_tem_mensagem_de_antecipacao():
    root, _ = _root(antecipacao_s=15)
    events = root.find("Events")
    msgs_antecipacao = [e for e in events if e.get("Type") == "Message" and e.get("Offset") == "-15"]
    steps = root.find("WorkoutSteps")
    # Uma mensagem "-15s" para cada bloco (o evento final tem offset positivo).
    assert len(msgs_antecipacao) == len(steps)


def test_esforcos_intensos_ganham_beep_e_countdown():
    root, _ = _root("TIROS", 62)  # sprints Z5 curtos (30s)
    events = root.find("Events")
    tipos = [e.get("Type") for e in events]
    assert "Beep" in tipos
    assert "Countdown" in tipos      # esforço curto (<=60s) e intenso (zona>=4)
    assert "Lap" in tipos            # volta automática no início de cada intervalo


def test_warmup_vira_ramp_e_esforco_vira_steady_em_watts():
    root, _ = _root("TIROS", 62)
    steps = list(root.find("WorkoutSteps"))
    assert steps[0].tag == "Ramp"                       # aquecimento é rampa
    assert int(steps[0].get("StartPower")) > 0          # com piso (Z1 começa em 0 W)
    assert int(steps[0].get("EndPower")) > int(steps[0].get("StartPower"))
    # O 1º sprint (Steady) tem potência dentro da zona 5 do atleta.
    z5 = _zonas_watts()[5]
    sprint = next(s for s in steps if s.tag == "Steady" and int(s.get("Duration")) == 30)
    assert z5["min"] <= int(sprint.get("Power")) <= z5["max"]


def test_cooldown_rampa_descendente():
    root, _ = _root("VO2MAX", 62)
    steps = list(root.find("WorkoutSteps"))
    cd = steps[-1]
    assert cd.tag == "Ramp"
    assert int(cd.get("StartPower")) > int(cd.get("EndPower"))  # desce


def test_evento_final_de_conclusao_perto_do_fim():
    root, _ = _root("VO2MAX", 62)
    steps = list(root.find("WorkoutSteps"))
    events = list(root.find("Events"))
    final = events[-1]
    assert "concluído" in final.get("Text").lower()
    assert final.get("StepId") == steps[-1].get("Id")
    assert int(final.get("Offset")) > 0  # offset positivo = dentro do último bloco


def test_tipo_sem_builder_retorna_none():
    assert build_erg_xml("NAO_EXISTE", 60, zonas_watts=_zonas_watts()) is None


def test_todos_os_tipos_de_bike_geram_xml_valido():
    for tipo in ("RECUPERACAO", "Z2_LONGO", "TEMPO", "FORCA", "TIROS", "VO2MAX", "TESTE_FTP"):
        xml = build_erg_xml(tipo, 60, zonas_watts=_zonas_watts(), ftp=FTP)
        assert xml is not None, tipo
        ET.fromstring(xml)  # não lança = bem-formado


def test_nome_e_descricao_sao_escapados():
    xml = build_erg_xml("TIROS", 62, zonas_watts=_zonas_watts(),
                         nome='Treino & <teste>', descricao='a < b & c')
    root = ET.fromstring(xml)  # não lança apesar dos caracteres especiais
    assert root.get("name") == "Treino & <teste>"
    assert root.find("Metadata/Description").text == "a < b & c"
