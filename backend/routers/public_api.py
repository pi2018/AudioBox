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
    """État complet du lecteur — pour Home Assistant, scripts, etc."""
    state = lecteur._etat_complet(await audio.get_status())
    config = load_config()
    state["abs_configured"] = bool(config.get("abs_url"))
    state["radios"] = [r.get("name", "") for r in config.get("radios", [])]
    # Pochette : une adresse de CETTE box (Home Assistant la récupère ici).
    if state.get("item_id"):
        state["image"] = f"/api/abs/cover/{state['item_id']}"
    else:
        state["image"] = state.get("cover_url") or ""
    return state


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
    await lecteur.play(lecteur.PlayRequest(source="radio", uri=station["url"],
                                           title=station["name"], cover_url=station.get("favicon", ""),
                                           output=config.get("default_output", "jack")))
    return {"status": "playing", "station": station["name"]}


@router.get("/radios")
async def list_radios():
    """Liste les radios disponibles."""
    config = load_config()
    return {"radios": [{"name": r["name"]} for r in config.get("radios", [])]}


# ── Pour Home Assistant : lire une adresse, faire une annonce ─────────────────
# Ces deux-là font télécharger une adresse à la box : elles demandent le code
# (Home Assistant l'envoie, réglé une fois dans l'intégration).
from fastapi import Depends, HTTPException
from pydantic import BaseModel
from routers.settings import verify_token
import asyncio


class LireRequest(BaseModel):
    url: str
    title: str = ""


@router.post("/play_url")
async def lire_adresse(req: LireRequest, _: bool = Depends(verify_token)):
    if not (req.url.startswith("http://") or req.url.startswith("https://")):
        raise HTTPException(status_code=400, detail="Adresse http(s) attendue")
    config = load_config()
    return await lecteur.play(lecteur.PlayRequest(source="url", uri=req.url, title=req.title or "Home Assistant",
                                                  output=config.get("default_output", "jack")))


@router.post("/annonce")
async def annonce(req: LireRequest, _: bool = Depends(verify_token)):
    """
    Joue un message (synthèse vocale de Home Assistant, sonnette…) puis reprend
    ce qui jouait avant, à la même position.
    """
    if not (req.url.startswith("http://") or req.url.startswith("https://")):
        raise HTTPException(status_code=400, detail="Adresse http(s) attendue")
    avant = lecteur._etat_complet(await audio.get_status())
    reprise = dict(lecteur.en_cours) if not avant.get("stopped") else None
    position = avant.get("position", 0) if reprise else 0
    config = load_config()
    sortie = config.get("default_output", "jack")

    # Envoyer la position du livre avant de couper.
    await lecteur.stop()
    await audio.play(req.url, sortie)
    await ws_mgr.broadcast({"event": "annonce"})
    # Attendre la fin du message (2 minutes au plus).
    for _ in range(240):
        await asyncio.sleep(0.5)
        st = await audio.get_status()
        if st.get("stopped"):
            break
    if reprise and reprise.get("uri"):
        await lecteur.play(lecteur.PlayRequest(
            source=reprise.get("source", ""), uri=reprise["uri"], output=reprise.get("output", sortie),
            start_time=position if reprise.get("source") in ("abs", "podcast", "nas", "youtube") else 0,
            title=reprise.get("title", ""), author=reprise.get("author", ""),
            cover_url=reprise.get("cover_url", ""), item_id=reprise.get("item_id", "")))
    return {"status": "ok", "repris": bool(reprise)}


@router.post("/suivant")
async def suivant():
    """Bouton « suivant » : +30 s dans un livre."""
    st = await audio.get_status()
    await audio.seek(min(st.get("duration", 0) or 0, st.get("position", 0) + 30))
    return {"status": "ok"}


@router.post("/precedent")
async def precedent():
    """Bouton « précédent » : −30 s dans un livre."""
    st = await audio.get_status()
    await audio.seek(max(0, st.get("position", 0) - 30))
    return {"status": "ok"}
