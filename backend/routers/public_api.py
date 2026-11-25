"""
API REST publique AudioBox — sans token, pour intégrations externes.
Endpoints en lecture/écriture limités aux actions de base.
"""
from fastapi import APIRouter
from services.audio_manager import AudioManager
from config import load_config
import logging

router = APIRouter(prefix="/public", tags=["public"])
logger = logging.getLogger("public_api")

# Référence partagée avec player.py. Lecture, pause et arrêt passent par ses
# fonctions : sinon l'envoi de la position à Audiobookshelf n'était pas suivi.
from routers import player as lecteur
from routers.player import audio, ws_mgr


@router.get("/state")
async def get_state():
    """État complet du player — pour HA, scripts, etc."""
    state  = await audio.get_status()
    config = load_config()
    return {
        "playing":    state.get("playing", False),
        "paused":     state.get("paused", False),
        "stopped":    state.get("stopped", True),
        "position":   state.get("position", 0),
        "duration":   state.get("duration", 0),
        "progress":   state.get("progress", 0),
        "volume":     state.get("volume", 80),
        "uri":        state.get("uri", ""),
        "source":     "unknown",
        "abs_configured": bool(config.get("abs_url")),
    }


@router.post("/play")
async def public_play():
    """Reprend la lecture."""
    return await lecteur.resume()


@router.post("/pause")
async def public_pause():
    """Met en pause."""
    return await lecteur.pause()


@router.post("/stop")
async def public_stop():
    """Arrête la lecture."""
    return await lecteur.stop()


@router.post("/volume/{level}")
async def public_volume(level: int):
    """Règle le volume (0-100)."""
    level = max(0, min(100, level))
    await audio.set_volume(level)
    return {"volume": level}


@router.post("/volume/up/{step}")
async def volume_up(step: int = 5):
    """Monte le volume."""
    state = await audio.get_status()
    new_vol = min(100, state.get("volume", 80) + step)
    await audio.set_volume(new_vol)
    return {"volume": new_vol}


@router.post("/volume/down/{step}")
async def volume_down(step: int = 5):
    """Baisse le volume."""
    state = await audio.get_status()
    new_vol = max(0, state.get("volume", 80) - step)
    await audio.set_volume(new_vol)
    return {"volume": new_vol}


@router.post("/seek/{seconds}")
async def public_seek(seconds: float):
    """Seek absolu en secondes."""
    await audio.seek(seconds)
    return {"position": seconds}


@router.post("/radio/{name}")
async def play_radio_by_name(name: str):
    """Lance une radio par son nom (recherche partielle)."""
    config = load_config()
    radios = config.get("radios", [])
    name_lower = name.lower()
    station = next(
        (r for r in radios if name_lower in r.get("name", "").lower()),
        None
    )
    if not station:
        return {"error": f"Radio '{name}' non trouvée", "available": [r["name"] for r in radios]}
    await audio.play(station["url"], config.get("default_output", "jack"))
    await ws_mgr.broadcast({"event": "play", "title": station["name"]})
    return {"status": "playing", "station": station["name"]}


@router.get("/radios")
async def list_radios():
    """Liste les radios disponibles."""
    config = load_config()
    return {"radios": [{"name": r["name"]} for r in config.get("radios", [])]}
