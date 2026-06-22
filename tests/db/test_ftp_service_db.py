"""Testes de integração para FTP e zonas de potência (config_service + MongoDB fake)."""
import pytest

from app.services import config_service, user_service


async def _criar_user(fake_db):
    u = await user_service.criar_usuario({
        "login": "ftp_user", "senha": "x", "nome": "FTP Tester",
        "telefone": "+5551999990001",
        "perfil": {"idade": 35, "peso_kg": 75, "altura_cm": 178, "fc_max": 185},
    })
    return str(u["_id"])


class TestGetFTP:
    async def test_sem_ftp_retorna_none(self, fake_db):
        uid = await _criar_user(fake_db)
        ftp, modo = await config_service.get_ftp(uid)
        assert ftp is None

    async def test_modo_default_e_indoor(self, fake_db):
        uid = await _criar_user(fake_db)
        _, modo = await config_service.get_ftp(uid)
        assert modo == "indoor"

    async def test_usuario_inexistente_retorna_none(self, fake_db):
        ftp, modo = await config_service.get_ftp("000000000000000000000000")
        assert ftp is None
        assert modo == "indoor"


class TestSalvarFTP:
    async def test_salva_e_retorna_ftp(self, fake_db):
        uid = await _criar_user(fake_db)
        resultado = await config_service.salvar_ftp(uid, 250)
        assert resultado["ftp"] == 250
        assert resultado["potencia_modo"] == "indoor"

    async def test_retorna_7_zonas(self, fake_db):
        uid = await _criar_user(fake_db)
        resultado = await config_service.salvar_ftp(uid, 280)
        assert len(resultado["zonas"]) == 7

    async def test_modo_sempre_persiste(self, fake_db):
        uid = await _criar_user(fake_db)
        await config_service.salvar_ftp(uid, 260, "sempre")
        ftp, modo = await config_service.get_ftp(uid)
        assert modo == "sempre"

    async def test_modo_invalido_vira_indoor(self, fake_db):
        uid = await _criar_user(fake_db)
        resultado = await config_service.salvar_ftp(uid, 260, "xpto")
        assert resultado["potencia_modo"] == "indoor"

    async def test_ftp_abaixo_50_lanca(self, fake_db):
        uid = await _criar_user(fake_db)
        with pytest.raises(ValueError, match="FTP inválido"):
            await config_service.salvar_ftp(uid, 40)

    async def test_ftp_acima_700_lanca(self, fake_db):
        uid = await _criar_user(fake_db)
        with pytest.raises(ValueError, match="FTP inválido"):
            await config_service.salvar_ftp(uid, 750)

    async def test_fronteira_50_aceita(self, fake_db):
        uid = await _criar_user(fake_db)
        r = await config_service.salvar_ftp(uid, 50)
        assert r["ftp"] == 50

    async def test_fronteira_700_aceita(self, fake_db):
        uid = await _criar_user(fake_db)
        r = await config_service.salvar_ftp(uid, 700)
        assert r["ftp"] == 700

    async def test_persiste_no_banco(self, fake_db):
        uid = await _criar_user(fake_db)
        await config_service.salvar_ftp(uid, 300, "nunca")
        ftp, modo = await config_service.get_ftp(uid)
        assert ftp == 300
        assert modo == "nunca"

    async def test_atualizar_ftp_sobrescreve(self, fake_db):
        uid = await _criar_user(fake_db)
        await config_service.salvar_ftp(uid, 250)
        await config_service.salvar_ftp(uid, 275)
        ftp, _ = await config_service.get_ftp(uid)
        assert ftp == 275


class TestGetZonasPotencia:
    async def test_sem_ftp_retorna_none(self, fake_db):
        uid = await _criar_user(fake_db)
        resultado = await config_service.get_zonas_potencia(uid)
        assert resultado is None

    async def test_com_ftp_retorna_estrutura(self, fake_db):
        uid = await _criar_user(fake_db)
        await config_service.salvar_ftp(uid, 254)
        zp = await config_service.get_zonas_potencia(uid)
        assert zp is not None
        assert zp["ftp"] == 254
        assert zp["potencia_modo"] == "indoor"
        assert len(zp["zonas"]) == 7

    async def test_zonas_contem_campos_obrigatorios(self, fake_db):
        uid = await _criar_user(fake_db)
        await config_service.salvar_ftp(uid, 300)
        zp = await config_service.get_zonas_potencia(uid)
        for z in zp["zonas"]:
            assert "zona" in z
            assert "min" in z
            assert "max" in z
            assert "nome" in z

    async def test_isola_por_usuario(self, fake_db):
        uid1 = await _criar_user(fake_db)
        uid2 = await user_service.criar_usuario({
            "login": "outro", "senha": "x", "nome": "Outro",
            "telefone": "+5551999990002",
            "perfil": {},
        })
        uid2 = str(uid2["_id"])
        await config_service.salvar_ftp(uid1, 280)
        # uid2 nunca salvou FTP
        assert await config_service.get_zonas_potencia(uid2) is None


class TestZonasDados:
    """get_zonas retorna FC e get_zonas_potencia retorna potência — integração conjunta."""

    async def test_zonas_fc_e_potencia_independentes(self, fake_db):
        uid = await _criar_user(fake_db)
        await config_service.salvar_ftp(uid, 260)
        await config_service.salvar_zonas(uid, {
            "fc_max": 185, "limiar": None,
            "zonas": [
                {"zona": 1, "min": 118, "max": 140},
                {"zona": 2, "min": 141, "max": 156},
                {"zona": 3, "min": 157, "max": 166},
                {"zona": 4, "min": 167, "max": 176},
                {"zona": 5, "min": 177, "max": 185},
            ],
        })
        fc = await config_service.get_zonas(uid)
        pot = await config_service.get_zonas_potencia(uid)
        assert len(fc["zonas"]) == 5
        assert len(pot["zonas"]) == 7
        assert pot["ftp"] == 260
