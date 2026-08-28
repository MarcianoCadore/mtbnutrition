"""Endpoint que alimenta o gráfico de estrutura do card (/workout/estrutura/...).

O portal manda junto a descrição que o atleta está lendo no modal: o desenho tem
que sair dela, não do molde do tipo.
"""

DESC = ("15 min aquecimento progressivo Z1→Z2. 3×15 min em Z3/Z4 com 5 min de "
        "recuperação Z1 entre cada bloco. 15 min volta à calma Z1.")


def _blocos(segs):
    return [s for s in segs if s["fase"] == "interval" and (s["zona"] or 0) >= 3]


class TestEstruturaDoGrafico:
    def test_desenha_a_serie_da_descricao(self, auth_client, fake_db, run):
        client, _ = auth_client
        r = client.get("/workout/estrutura/TEMPO", params={"duracao_min": 100, "descricao": DESC})
        assert r.status_code == 200
        segs = r.json()["segments"]
        assert len(_blocos(segs)) == 3
        assert {b["duracao_s"] for b in _blocos(segs)} == {900}
        assert sum(s["duracao_s"] for s in segs) == r.json()["total_s"] == 100 * 60

    def test_sem_descricao_cai_no_molde(self, auth_client, fake_db, run):
        client, _ = auth_client
        r = client.get("/workout/estrutura/TEMPO", params={"duracao_min": 100})
        assert r.status_code == 200
        assert len(_blocos(r.json()["segments"])) == 5

    def test_tipo_sem_estrutura_404(self, auth_client, fake_db, run):
        client, _ = auth_client
        assert client.get("/workout/estrutura/NAO_EXISTE").status_code == 404
