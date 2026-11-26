"""
Essais avec le vrai mpv (sans haut-parleur) : plusieurs demandes en même temps.
python3 -m pytest backend/tests
"""
import asyncio
import os
import shutil
import subprocess
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.audio_manager import AudioManager  # noqa: E402

pytestmark = pytest.mark.skipif(not (shutil.which("mpv") and shutil.which("ffmpeg")),
                                reason="mpv et ffmpeg nécessaires")


@pytest.fixture
def morceau(tmp_path, monkeypatch):
    # mpv sans carte son : sortie « null ».
    (tmp_path / "mpv").mkdir()
    (tmp_path / "mpv" / "mpv.conf").write_text("ao=null\n")
    monkeypatch.setenv("MPV_HOME", str(tmp_path / "mpv"))
    fichier = tmp_path / "son.mp3"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=30",
                    "-q:a", "9", str(fichier)], check=True)
    return str(fichier)


def test_demandes_simultanees_toutes_servies(morceau):
    async def scenario():
        a = AudioManager()
        await a.play(morceau, start_time=5)
        await asyncio.sleep(1.5)
        debut = time.monotonic()
        etats = await asyncio.gather(*[a.get_status() for _ in range(20)])
        duree = time.monotonic() - debut
        await a.stop()
        return etats, duree
    etats, duree = asyncio.run(scenario())
    # Avant (1.5) : des positions à 0 et 2 s d'attente par réponse perdue.
    assert all(e["position"] >= 5 for e in etats), [e["position"] for e in etats]
    assert all(e["duration"] > 25 for e in etats), [e["duration"] for e in etats]
    assert duree < 1.5, duree


def test_charge_en_pause(morceau):
    async def scenario():
        a = AudioManager()
        await a.play(morceau, start_time=10, en_pause=True)
        await asyncio.sleep(1.0)
        e1 = await a.get_status()
        await asyncio.sleep(1.0)
        e2 = await a.get_status()
        await a.stop()
        return e1, e2
    e1, e2 = asyncio.run(scenario())
    assert e1["paused"] and not e1["playing"]
    assert abs(e2["position"] - e1["position"]) < 0.2 and e1["position"] >= 9.5


def test_deux_lancements_en_meme_temps_un_seul_mpv(morceau):
    async def scenario():
        a = AudioManager()
        await asyncio.gather(a.play(morceau), a.play(morceau, start_time=3))
        await asyncio.sleep(0.5)
        restants = subprocess.run(["pgrep", "-c", "-f", "input-ipc-server=/tmp/jv-mpv.sock"],
                                  capture_output=True, text=True).stdout.strip()
        await a.stop()
        return int(restants or 0)
    # Avant : deux mpv, dont un qu'on ne pouvait plus arrêter.
    assert asyncio.run(scenario()) == 1
