"""
Ce que l'appli du téléphone demande à la box : livres, lancer un livre, radios.
python3 -m pytest backend/tests
"""
import asyncio
import os
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routers import abs as absr  # noqa: E402
from routers import public_api, player  # noqa: E402
from services import abs_sync  # noqa: E402
from tests.test_lecteur import FauxMpv  # noqa: E402

CFG = {"abs_url": "http://abs", "abs_api_key": "cle", "radios": [{"name": "FIP", "url": "http://r/fip"}]}

ITEMS = [
    {"id": "l1", "media": {"duration": 1000, "metadata": {"title": "Zadig", "authorName": "Voltaire"}}},
    {"id": "l2", "media": {"duration": 2000, "metadata": {"title": "Les Misérables", "authorName": "Victor Hugo"}}},
    {"id": "l3", "media": {"duration": 500, "metadata": {"title": "Candide", "authorName": "Voltaire"}}},
]
PROGRES = [{"libraryItemId": "l2", "progress": 0.4, "isFinished": False, "lastUpdate": 50},
           {"libraryItemId": "l3", "progress": 1.0, "isFinished": True, "lastUpdate": 99},
           {"libraryItemId": "l1", "progress": 0.1, "isFinished": False, "lastUpdate": 80}]


@pytest.fixture
def banc(monkeypatch):
    cfg = {**CFG, "radios": list(CFG["radios"])}
    mpv = FauxMpv()
    lances = []

    async def abs_get(chemin, params=None):
        if chemin == "/api/libraries":
            return {"libraries": [{"id": "L", "mediaType": "book"}]}
        if chemin == "/api/me":
            return {"mediaProgress": PROGRES, "token": "SECRET"}
        if chemin.endswith("/items"):
            return {"results": ITEMS}
        raise AssertionError(chemin)

    async def lancer(req, en_pause=False):
        lances.append(req)
        return {"status": "playing"}

    async def flux(item_id, file_id=""):
        return {"url": f"http://abs/api/items/{item_id}/file/1", "title": "Zadig", "duration": 1000, "item_id": item_id}

    async def item(item_id):
        return ITEMS[0]

    async def position(item_id):
        return banc.position

    class B:
        pass
    banc = B()
    banc.position, banc.lances, banc.cfg = 120.0, lances, cfg
    monkeypatch.setattr(absr, "_abs_get", abs_get)
    monkeypatch.setattr(absr, "stream_item", flux)
    monkeypatch.setattr(absr, "get_item", item)
    monkeypatch.setattr(abs_sync, "get_server_position", position)
    monkeypatch.setattr(public_api.lecteur, "lancer", lancer)
    monkeypatch.setattr(public_api, "load_config", lambda: cfg)
    monkeypatch.setattr(public_api, "update_config", lambda u: cfg.update(u) or cfg)
    public_api._cache_livres.update({"quand": 0.0, "livres": []})
    return banc


def test_liste_et_progression(banc):
    r = asyncio.run(public_api.liste_livres())
    assert r["total"] == 3 and r["configure"]
    assert [x["id"] for x in r["en_cours"]] == ["l1", "l2"]       # Candide fini : absent
    assert {x["id"]: x["progression"] for x in r["livres"]}["l2"] == 0.4
    assert "SECRET" not in str(r)


def test_recherche_titre_ou_auteur(banc):
    r = asyncio.run(public_api.liste_livres(q="voltaire"))
    assert sorted(x["id"] for x in r["livres"]) == ["l1", "l3"] and r["en_cours"] == []
    assert asyncio.run(public_api.liste_livres(q="miser"))["total"] == 1
    assert [x["id"] for x in asyncio.run(public_api.liste_livres(q="miser"))["livres"]] == ["l2"]


def test_abs_non_configure(banc):
    banc.cfg.pop("abs_api_key")
    r = asyncio.run(public_api.liste_livres())
    assert r["livres"] == [] and r["configure"] is False


def test_lancer_livre_reprend_a_sa_place(banc):
    r = asyncio.run(public_api.lancer_livre("l1"))
    req = banc.lances[-1]
    assert req.source == "abs" and req.item_id == "l1" and req.start_time == 120.0
    assert req.author == "Voltaire" and r["status"] == "playing"


def test_livre_fini_repart_du_debut(banc):
    banc.position = 995.0
    asyncio.run(public_api.lancer_livre("l1"))
    assert banc.lances[-1].start_time == 0.0


def test_ajouter_et_supprimer_une_radio(banc):
    r = asyncio.run(public_api.ajouter_radio(public_api.NouvelleRadio(
        name="  Radio\x00 Nova ", url="https://nova/stream", favicon="pas-une-adresse")))
    assert r["radios"] == ["FIP", "Radio Nova"]
    assert banc.cfg["radios"][1]["favicon"] == ""
    # même nom (majuscules différentes) : remplacée, pas doublée
    asyncio.run(public_api.ajouter_radio(public_api.NouvelleRadio(name="radio nova", url="http://autre/s")))
    assert [x["name"] for x in banc.cfg["radios"]] == ["FIP", "radio nova"]
    r = asyncio.run(public_api.supprimer_radio("RADIO NOVA"))
    assert r["radios"] == ["FIP"]


def test_radio_refus(banc):
    with pytest.raises(HTTPException) as e:
        asyncio.run(public_api.ajouter_radio(public_api.NouvelleRadio(name="X", url="file:///etc/passwd")))
    assert e.value.status_code == 400
    with pytest.raises(HTTPException) as e:
        asyncio.run(public_api.ajouter_radio(public_api.NouvelleRadio(name="  ", url="http://x/y")))
    assert e.value.status_code == 400
    with pytest.raises(HTTPException) as e:
        asyncio.run(public_api.supprimer_radio("inconnue"))
    assert e.value.status_code == 404


def test_radios_depuis_le_telephone_sans_code(banc):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(public_api.router, prefix="/api")
    c = TestClient(app, client=("192.168.178.50", 5555))
    assert c.post("/api/public/radios", json={"name": "A", "url": "http://a/b"}).status_code == 200
    assert c.delete("/api/public/radios/A").status_code == 200
    # mais ce qui fait télécharger une adresse reste protégé
    assert c.post("/api/public/play_url", json={"url": "http://a/b"}).status_code == 401
