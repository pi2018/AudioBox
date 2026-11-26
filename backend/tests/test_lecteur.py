"""
Essais du lecteur avec un faux mpv : changement de livre, minuterie, reprise, annonces.
python3 -m pytest backend/tests
"""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routers import player, public_api  # noqa: E402
from services import abs_sync, webhooks  # noqa: E402

REGLAGES = {"abs_url": "http://abs", "abs_api_key": "cle",
            "radios": [{"name": "FIP Jazz", "url": "http://radio/fipjazz"},
                       {"name": "FIP", "url": "http://radio/fip", "favicon": "http://radio/fip.png"}]}


class FauxMpv:
    """Ce que le serveur attend de mpv, sans le son."""
    def __init__(self):
        self.vitesse = 1.0
        self._volume = 80
        self.uri = None
        self.position = 0.0
        self.en_pause = False
        self.lances = []

    async def play(self, uri, output="jack", start_time=0.0, http_token="", vitesse=1.0, en_pause=False):
        self.lances.append({"uri": uri, "start": start_time, "en_pause": en_pause, "jeton": http_token})
        self.uri, self.position, self.en_pause = uri, start_time, en_pause

    async def stop(self):
        self.uri, self.en_pause = None, False

    async def pause(self):
        self.en_pause = True

    async def resume(self):
        self.en_pause = False

    async def seek(self, p):
        self.position = p

    async def set_volume(self, v):
        self._volume = v

    async def set_speed(self, s):
        self.vitesse = s

    async def set_equalizer(self, af):
        pass

    async def get_status(self):
        joue = self.uri is not None
        return {"playing": joue and not self.en_pause, "paused": joue and self.en_pause,
                "stopped": not joue, "uri": self.uri or "",
                "position": self.position if joue else 0.0,
                "duration": 3600.0 if joue else 0.0, "volume": self._volume, "progress": 0}


class Banc:
    def __init__(self):
        self.audio = FauxMpv()
        self.envois = []          # (livre, position) envoyés à Audiobookshelf
        self.position_serveur = 0.0


@pytest.fixture
def banc(monkeypatch):
    b = Banc()
    monkeypatch.setattr(player, "audio", b.audio)
    monkeypatch.setattr(public_api, "audio", b.audio)
    monkeypatch.setattr(player, "load_config", lambda: REGLAGES)
    monkeypatch.setattr(public_api, "load_config", lambda: REGLAGES)

    async def envoyer(item_id, position, duration, is_finished=False):
        b.envois.append((item_id, position))

    async def position_serveur(item_id):
        return b.position_serveur

    async def rien(*a, **k):
        return None

    monkeypatch.setattr(abs_sync, "_send_progress", envoyer)
    monkeypatch.setattr(abs_sync, "get_server_position", position_serveur)
    monkeypatch.setattr(webhooks, "fire", rien)
    # La synchro démarre tout de suite (au lieu de 8 s) pour être en plein travail.
    depart = abs_sync.start_sync
    monkeypatch.setattr(abs_sync, "start_sync",
                        lambda item, audio, start_position=0.0, attente=8: depart(item, audio, start_position, 0.01))
    player._current_item_id = None
    player.en_cours.clear()
    player._sommeil, player._sommeil_fin = None, 0.0
    yield b
    abs_sync.stop_sync()


def livre(item, debut=0.0, **k):
    return player.PlayRequest(source="abs", uri=f"http://abs/api/items/{item}/file/1",
                              item_id=item, start_time=debut, **k)


def test_changer_de_livre_ne_touche_pas_l_ancien(banc):
    async def scenario():
        await player.lancer(livre("A", 30))
        await asyncio.sleep(0.05)          # la synchro de A tourne
        banc.audio.position = 45.0         # A a avancé
        await player.lancer(livre("B", 900))
        await asyncio.sleep(0.05)
    asyncio.run(scenario())
    # A reçoit SA position finale, et jamais celle de B (avant : 900 écrasait A).
    assert [p for (i, p) in banc.envois if i == "A"] == [45.0]


def test_cle_abs_seulement_vers_abs(banc):
    async def scenario():
        await player.lancer(livre("A"))
        await player.lancer(player.PlayRequest(source="abs", uri="http://ailleurs/x.mp3"))
    asyncio.run(scenario())
    assert banc.audio.lances[0]["jeton"] == "cle"
    assert banc.audio.lances[1]["jeton"] == ""


def test_minuterie_changee_garde_son_temps(banc):
    async def scenario():
        await player.minuterie(player.SommeilRequest(minutes=30))
        await asyncio.sleep(0.01)
        await player.minuterie(player.SommeilRequest(minutes=15))
        await asyncio.sleep(0.05)          # l'ancienne minuterie finit de s'annuler
        reste = player.sommeil_reste()
        await player.minuterie(player.SommeilRequest(minutes=0))
        return reste
    # Avant (1.5) : 0, la nouvelle minuterie était effacée par l'ancienne.
    assert 890 <= asyncio.run(scenario()) <= 900


def test_annuler_pendant_la_baisse_remet_le_volume(banc, monkeypatch):
    monkeypatch.setattr(player, "PAS", 0.01)

    async def scenario():
        await player.lancer(player.PlayRequest(source="radio", uri="http://radio/fip"))
        player._sommeil = tache = asyncio.create_task(player._dormir(0.3))
        await asyncio.sleep(0.12)
        baisse = banc.audio._volume
        tache.cancel()
        await asyncio.sleep(0.05)
        return baisse, banc.audio._volume, banc.audio.uri
    baisse, apres, uri = asyncio.run(scenario())
    assert baisse < 80 and apres == 80 and uri == "http://radio/fip"


def test_minuterie_jusqu_au_bout(banc, monkeypatch):
    monkeypatch.setattr(player, "PAS", 0.01)

    async def scenario():
        await player.lancer(player.PlayRequest(source="radio", uri="http://radio/fip"))
        await player.minuterie(player.SommeilRequest(minutes=1))
        player._sommeil.cancel()           # on remplace par une minuterie très courte
        player._sommeil = asyncio.create_task(player._dormir(0.3))
        await asyncio.sleep(0.6)
        return banc.audio.uri, banc.audio._volume, player.sommeil_reste()
    uri, volume, reste = asyncio.run(scenario())
    assert uri is None and volume == 80 and reste == 0


def test_lecture_apres_arret_reprend_la_radio(banc):
    async def scenario():
        await player.lancer(player.PlayRequest(source="radio", uri="http://radio/fip", title="FIP"))
        await player.stop()
        etat = player._etat_complet(await banc.audio.get_status())
        r = await player.resume()
        return etat, r
    etat, r = asyncio.run(scenario())
    assert etat["dernier"] == "FIP"
    assert r["status"] == "playing"
    assert banc.audio.lances[-1]["uri"] == "http://radio/fip" and banc.audio.lances[-1]["start"] == 0


def test_lecture_apres_arret_reprend_le_livre_a_sa_position(banc):
    banc.position_serveur = 1234.0

    async def scenario():
        await player.lancer(livre("A", 30))
        await player.stop()
        await player.resume()
    asyncio.run(scenario())
    assert banc.audio.lances[-1]["start"] == 1234.0
    assert player._current_item_id == "A"


def test_rien_a_reprendre(banc):
    with pytest.raises(player.HTTPException) as e:
        asyncio.run(player.resume())
    assert e.value.status_code == 409


def test_annonce_remet_le_livre_en_pause_au_bon_endroit(banc):
    async def scenario():
        await player.lancer(livre("A", 100))
        banc.audio.position = 120.0
        await player.pause()
        jouer = banc.audio.play

        async def play(uri, *a, **k):
            await jouer(uri, *a, **k)
            if "annonce" in uri:             # le message joue, puis s'arrête tout seul
                banc.audio.position = 0.5
                asyncio.get_running_loop().call_later(0.8, lambda: setattr(banc.audio, "uri", None))
        banc.audio.play = play
        return await public_api.annonce(public_api.LireRequest(url="http://ha/annonce.mp3"), True)
    r = asyncio.run(scenario())
    assert r == {"status": "ok", "repris": True}
    dernier = banc.audio.lances[-1]
    assert dernier["uri"].endswith("/A/file/1") and dernier["start"] == 120.0
    assert dernier["en_pause"] is True     # avant : le livre repartait tout seul
    assert banc.audio.lances[-2]["uri"] == "http://ha/annonce.mp3"


def test_radio_par_nom_exact_d_abord(banc):
    async def scenario():
        return await public_api.play_radio_by_name("FIP")
    r = asyncio.run(scenario())
    assert r["station"] == "FIP"            # avant : « FIP Jazz », la première qui contient « fip »
    assert banc.audio.lances[-1]["uri"] == "http://radio/fip"
    assert player.en_cours["cover_url"] == "http://radio/fip.png"
