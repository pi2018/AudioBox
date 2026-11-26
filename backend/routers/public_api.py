"""
API REST publique AudioBox — sans code, pour Home Assistant, l'appli du téléphone et
les scripts : état, lecture, pause, volume, radios. Ce qui fait télécharger une adresse
à la box (lire une adresse, faire une annonce) demande le code admin.
"""
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from config import load_config
# Lecture, pause et arrêt passent par les fonctions du lecteur : sinon l'envoi de la
# position à Audiobookshelf n'était pas suivi.
from routers import player as lecteur
from routers.player import audio, ws_mgr
from routers.settings import verify_token

router = APIRouter(prefix="/public", tags=["public"])
logger = logging.getLogger("public_api")


@router.get("/state")
async def get_state():
    """État complet du lecteur — pour Home Assistant, l'appli, les scripts."""
    state = lecteur._etat_complet(await audio.get_status())
    config = load_config()
    state["abs_configured"] = bool(config.get("abs_url"))
    state["radios"] = [r.get("name", "") for r in config.get("radios", []) if r.get("name")]
    # Pochette : une adresse de CETTE box (Home Assistant et l'appli la récupèrent ici).
    if state.get("item_id"):
        state["image"] = f"/api/abs/cover/{state['item_id']}"
    else:
        state["image"] = state.get("cover_url") or ""
    return state


@router.post("/play")
async def public_play():
    """Reprend la lecture ; si tout est arrêté, relance la dernière écoute."""
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
    new_vol = min(100, state.get("volume", 80) + abs(step))
    await audio.set_volume(new_vol)
    return {"volume": new_vol}


@router.post("/volume/down/{step}")
async def volume_down(step: int = 5):
    """Baisse le volume."""
    state = await audio.get_status()
    new_vol = max(0, state.get("volume", 80) - abs(step))
    await audio.set_volume(new_vol)
    return {"volume": new_vol}


@router.post("/seek/{seconds}")
async def public_seek(seconds: float):
    """Seek absolu en secondes."""
    seconds = max(0.0, seconds)
    await audio.seek(seconds)
    return {"position": seconds}


def _radios_valides(config: dict) -> list[dict]:
    return [r for r in config.get("radios", []) if r.get("name") and r.get("url")]


@router.post("/radio/{name:path}")
async def play_radio_by_name(name: str):
    """
    Lance une radio par son nom. Le nom exact d'abord : avant, « FIP » pouvait lancer
    « FIP Jazz » (la première radio dont le nom CONTIENT « fip »), par exemple quand
    Home Assistant choisissait une source.
    """
    config = load_config()
    radios = _radios_valides(config)
    cherche = name.strip().lower()
    station = (next((r for r in radios if r["name"].strip().lower() == cherche), None)
               or next((r for r in radios if cherche and cherche in r["name"].lower()), None))
    if not station:
        return {"error": f"Radio '{name}' non trouvée", "available": [r["name"] for r in radios]}
    await lecteur.lancer(lecteur.PlayRequest(
        source="radio", uri=station["url"], title=station["name"],
        cover_url=station.get("favicon", ""), output=config.get("default_output", "jack")))
    return {"status": "playing", "station": station["name"]}


@router.get("/radios")
async def list_radios():
    """Liste les radios disponibles."""
    return {"radios": [{"name": r["name"]} for r in _radios_valides(load_config())]}


# ── Pour Home Assistant : lire une adresse, faire une annonce ─────────────────
# Ces deux-là font télécharger une adresse à la box : elles demandent le code
# (Home Assistant l'envoie, réglé une fois dans l'intégration).

class LireRequest(BaseModel):
    url: str
    title: str = ""


def _adresse_web(url: str) -> str:
    url = (url or "").strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(status_code=400, detail="Adresse http(s) attendue")
    return url


@router.post("/play_url")
async def lire_adresse(req: LireRequest, _: bool = Depends(verify_token)):
    config = load_config()
    return await lecteur.lancer(lecteur.PlayRequest(
        source="url", uri=_adresse_web(req.url), title=req.title or "Home Assistant",
        output=config.get("default_output", "jack")))


# Une annonce à la fois : deux annonces en même temps se coupaient l'une l'autre.
_verrou_annonce = asyncio.Lock()


@router.post("/annonce")
async def annonce(req: LireRequest, _: bool = Depends(verify_token)):
    """
    Joue un message (synthèse vocale de Home Assistant, sonnette…) puis remet ce qui
    jouait avant, à la même position, et en pause si c'était en pause.
    """
    url = _adresse_web(req.url)
    async with _verrou_annonce:
        avant = lecteur._etat_complet(await audio.get_status())
        reprise = dict(lecteur.en_cours) if not avant.get("stopped") else None
        position = avant.get("position", 0) if reprise else 0
        etait_en_pause = bool(avant.get("paused"))
        sortie = load_config().get("default_output", "jack")

        # Envoie la position du livre avant de couper.
        await lecteur.stop()
        ancien = dict(lecteur.en_cours)
        lecteur.en_cours.clear()
        lecteur.en_cours.update({"source": "annonce", "title": req.title or "Annonce", "uri": ""})
        try:
            await audio.play(url, sortie)
            await ws_mgr.broadcast({"event": "annonce"})
            # Le message démarre (Home Assistant prépare parfois la voix pendant
            # quelques secondes), puis on attend sa fin : 5 minutes au plus (avant :
            # 2 minutes, un long message était coupé ; et une adresse qui ne répond
            # pas bloquait tout 2 minutes, maintenant 20 secondes).
            demarre = False
            for _ in range(40):                 # 20 s au plus pour démarrer
                await asyncio.sleep(0.5)
                st = await audio.get_status()
                if st.get("stopped"):
                    break                       # fini (message très court) ou illisible
                if st.get("position", 0) > 0 or st.get("duration", 0) > 0:
                    demarre = True
                    break
            if demarre:
                for _ in range(600):            # 5 minutes au plus
                    await asyncio.sleep(0.5)
                    if (await audio.get_status()).get("stopped"):
                        break
        except Exception as e:
            logger.warning(f"Annonce non jouée : {e}")
        finally:
            await audio.stop()
            lecteur.en_cours.clear()
            lecteur.en_cours.update(ancien)

        repris = False
        if reprise and reprise.get("uri"):
            source = reprise.get("source", "")
            try:
                await lecteur.lancer(lecteur.PlayRequest(
                    source=source, uri=reprise["uri"], output=reprise.get("output", sortie),
                    start_time=position if source in lecteur.REPRISE_A_LA_POSITION else 0,
                    title=reprise.get("title", ""), author=reprise.get("author", ""),
                    cover_url=reprise.get("cover_url", ""), item_id=reprise.get("item_id", ""),
                    page=reprise.get("page", "")),
                    en_pause=etait_en_pause)
                repris = True
            except HTTPException as e:
                logger.warning(f"Reprise après l'annonce impossible : {e.detail}")
        return {"status": "ok", "repris": repris}


@router.post("/suivant")
async def suivant():
    """Bouton « suivant » : +30 s dans un livre."""
    st = await audio.get_status()
    if st.get("duration"):
        await audio.seek(min(st["duration"], st.get("position", 0) + 30))
    return {"status": "ok"}


@router.post("/precedent")
async def precedent():
    """Bouton « précédent » : −30 s dans un livre."""
    st = await audio.get_status()
    if st.get("duration"):
        await audio.seek(max(0, st.get("position", 0) - 30))
    return {"status": "ok"}
