"""Múltiplos treinos por dia: um "extra" (origem="extra") é um segundo (ou
terceiro) treino no mesmo dia, gerido só manualmente pelo usuário no painel —
nunca sincroniza com o Garmin, nunca é tocado pelo botão "Salvar Semana" nem
pela IA. Estes testes cobrem que criar/editar/apagar um extra nunca corrompe
o treino principal (nem outro extra) da mesma data, e que os fluxos de
escrita em massa (salvar semana, enviar pro Garmin, teste de FTP) preservam
extras existentes em vez de apagá-los silenciosamente.
"""
import pytest

SEG = "2026-06-22"  # segunda
QUA = "2026-06-24"  # quarta


class TestCriarEditarRemoverExtra:
    def test_criar_extra_nao_altera_primary(self, auth_client, fake_db, run):
        client, uid = auth_client
        run(fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": uid, "objetivo": "",
            "treinos": [{"data": QUA, "tipo": "TIROS", "duracao_min": 60}],
        }))

        r = client.post(f"/workout/treino/{SEG}/{QUA}/extra", json={
            "tipo": "ACADEMIA", "duracao_min": 60, "descricao": "Agachamento 4x8",
        })
        assert r.status_code == 200
        extra_id = r.json()["id"]

        doc = run(fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": uid}))
        primario = next(t for t in doc["treinos"] if t.get("origem") != "extra")
        extra = next(t for t in doc["treinos"] if t.get("origem") == "extra")
        assert primario == {"data": QUA, "tipo": "TIROS", "duracao_min": 60}
        assert extra["id"] == extra_id
        assert extra["tipo"] == "ACADEMIA"

    def test_patch_extra_so_afeta_o_extra(self, auth_client, fake_db, run):
        client, uid = auth_client
        run(fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": uid, "objetivo": "",
            "treinos": [{"data": QUA, "tipo": "TIROS", "duracao_min": 60}],
        }))
        r = client.post(f"/workout/treino/{SEG}/{QUA}/extra", json={
            "tipo": "ACADEMIA", "duracao_min": 60, "descricao": "Agachamento 4x8",
        })
        extra_id = r.json()["id"]

        r2 = client.patch(f"/workout/treino/{SEG}/{QUA}/extra/{extra_id}", json={
            "duracao_min": 45, "concluido": True,
        })
        assert r2.status_code == 200

        doc = run(fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": uid}))
        primario = next(t for t in doc["treinos"] if t.get("origem") != "extra")
        extra = next(t for t in doc["treinos"] if t.get("origem") == "extra")
        assert primario["duracao_min"] == 60          # primário intocado
        assert extra["duracao_min"] == 45
        assert extra["concluido"] is True

    def test_patch_extra_inexistente_404(self, auth_client, fake_db, run):
        client, uid = auth_client
        run(fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": uid, "objetivo": "", "treinos": [],
        }))
        r = client.patch(f"/workout/treino/{SEG}/{QUA}/extra/nao-existe", json={"duracao_min": 30})
        assert r.status_code == 404

    def test_delete_extra_por_id_nao_afeta_outro_extra_mesma_data(self, auth_client, fake_db, run):
        client, uid = auth_client
        run(fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": uid, "objetivo": "",
            "treinos": [{"data": QUA, "tipo": "TIROS", "duracao_min": 60}],
        }))
        r1 = client.post(f"/workout/treino/{SEG}/{QUA}/extra", json={"tipo": "ACADEMIA", "duracao_min": 60})
        r2 = client.post(f"/workout/treino/{SEG}/{QUA}/extra", json={"tipo": "RECUPERACAO", "duracao_min": 20})
        id1, id2 = r1.json()["id"], r2.json()["id"]

        r = client.delete(f"/workout/treino/{SEG}/{QUA}/extra/{id1}")
        assert r.status_code == 200

        doc = run(fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": uid}))
        extras = [t for t in doc["treinos"] if t.get("origem") == "extra"]
        assert len(extras) == 1
        assert extras[0]["id"] == id2
        primario = next(t for t in doc["treinos"] if t.get("origem") != "extra")
        assert primario["tipo"] == "TIROS"

    def test_delete_extra_inexistente_404(self, auth_client, fake_db, run):
        client, uid = auth_client
        run(fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": uid, "objetivo": "", "treinos": [],
        }))
        r = client.delete(f"/workout/treino/{SEG}/{QUA}/extra/nao-existe")
        assert r.status_code == 404


class TestFluxosEmMassaPreservamExtra:
    def test_salvar_semana_preserva_extra(self, auth_client, fake_db, run):
        client, uid = auth_client
        run(fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": uid, "objetivo": "",
            "treinos": [
                {"data": QUA, "tipo": "TIROS", "duracao_min": 60},
                {"data": QUA, "tipo": "ACADEMIA", "duracao_min": 60,
                 "descricao": "Academia", "origem": "extra", "id": "extra-1"},
            ],
        }))

        # Payload típico do botão "Salvar Semana" — só os 7 primários, sem o extra.
        r = client.post("/workout/semana", json={
            "semana_inicio": SEG, "objetivo": "",
            "treinos": [{"data": QUA, "tipo": "TIROS", "duracao_min": 60}],
        })
        assert r.status_code == 200

        doc = run(fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": uid}))
        extras = [t for t in doc["treinos"] if t.get("origem") == "extra"]
        assert len(extras) == 1
        assert extras[0]["id"] == "extra-1"

    def test_enviar_garmin_preserva_extra(self, auth_client, fake_db, run, monkeypatch):
        import app.services.garmin_workout_service as gws

        async def _fake_upload(user_id, *, tipo, duracao_min, nome, data_iso, descricao=None, **_):
            return None  # ACADEMIA/DESCANSO já são pulados; irrelevante aqui

        async def _fake_deletar(user_id, gid):
            return True

        monkeypatch.setattr(gws, "upload_e_agendar", _fake_upload)
        monkeypatch.setattr(gws, "deletar_workout_garmin", _fake_deletar)

        client, uid = auth_client
        run(fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": uid, "objetivo": "",
            "treinos": [
                {"data": QUA, "tipo": "TIROS", "duracao_min": 60},
                {"data": QUA, "tipo": "ACADEMIA", "duracao_min": 60,
                 "descricao": "Academia", "origem": "extra", "id": "extra-1"},
            ],
        }))

        r = client.post("/workout/enviar-garmin", json={
            "semana_inicio": SEG, "objetivo": "",
            "treinos": [{"data": QUA, "tipo": "TIROS", "duracao_min": 60}],
        })
        assert r.status_code == 200

        doc = run(fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": uid}))
        extras = [t for t in doc["treinos"] if t.get("origem") == "extra"]
        assert len(extras) == 1
        assert extras[0]["id"] == "extra-1"

    def test_reenviar_garmin_nao_envia_extra_ao_garmin(self, auth_client, fake_db, run, monkeypatch):
        import app.services.garmin_workout_service as gws

        chamadas = {"enviados": []}

        async def _fake_upload(user_id, *, tipo, duracao_min, nome, data_iso, descricao=None, **_):
            chamadas["enviados"].append(data_iso)
            return f"gid-{data_iso}"

        async def _fake_deletar(user_id, gid):
            return True

        monkeypatch.setattr(gws, "upload_e_agendar", _fake_upload)
        monkeypatch.setattr(gws, "deletar_workout_garmin", _fake_deletar)

        client, uid = auth_client
        # O extra tem tipo/duração de bike (não ACADEMIA) — se não fosse filtrado
        # por origem, o loop de reenvio o enviaria pro Garmin de verdade.
        run(fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": uid, "objetivo": "",
            "treinos": [
                {"data": QUA, "tipo": "TIROS", "duracao_min": 60},
                {"data": "2026-06-26", "tipo": "Z2_LONGO", "duracao_min": 90,
                 "origem": "extra", "id": "extra-1"},
            ],
        }))

        r = client.post(f"/workout/reenviar-garmin/{SEG}")
        assert r.status_code == 200
        assert "2026-06-26" not in chamadas["enviados"]
        assert QUA in chamadas["enviados"]

    def test_criar_ftp_nao_sobrescreve_extra_na_mesma_data(self, auth_client, fake_db, run, monkeypatch):
        import app.services.garmin_workout_service as gws

        async def _fake_upload(*a, **k):
            return "gid-ftp"

        monkeypatch.setattr(gws, "upload_e_agendar", _fake_upload)

        client, uid = auth_client
        run(fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": uid, "objetivo": "",
            "treinos": [{
                "data": QUA, "tipo": "ACADEMIA", "duracao_min": 60,
                "descricao": "Academia", "origem": "extra", "id": "extra-1",
            }],
        }))

        r = client.post("/workout/criar-ftp", json={"data": QUA, "duracao_min": 62})
        assert r.status_code == 200

        doc = run(fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": uid}))
        extras = [t for t in doc["treinos"] if t.get("origem") == "extra"]
        primarios = [t for t in doc["treinos"] if t.get("origem") != "extra"]
        assert len(extras) == 1 and extras[0]["id"] == "extra-1"
        assert len(primarios) == 1 and primarios[0]["tipo"] == "TESTE_FTP"

    def test_apagar_primeira_semana_bloqueia_se_houver_extra(self, auth_client, fake_db, run):
        client, uid = auth_client
        run(fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": uid, "objetivo": "", "origem": "auto",
            "treinos": [{
                "data": QUA, "tipo": "ACADEMIA", "duracao_min": 60,
                "origem": "extra", "id": "extra-1",
            }],
        }))
        r = client.delete(f"/workout/primeira-semana/{SEG}")
        assert r.status_code == 409

        doc = run(fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": uid}))
        assert doc is not None  # não foi apagada
