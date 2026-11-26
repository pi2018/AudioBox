import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from pydantic import BaseModel
import asyncio, logging
from services.audio_manager import AudioManager
from services.ws_manager import WSManager
from services import abs_sync, webhooks, montage
from config import load_config
from routers.nas import _is_safe_path

router  = APIRouter(prefix="/player", tags=["player"])
audio   = AudioManager()
ws_mgr  = WSManager()
logger  = logging.getLogger("player")

# Session de lecture courante
_current_item_id = None
# Ce qui joue (titre, auteur, pochette, source) : pour l'écran et Home Assistant.
en_cours: dict = {}


class PlayRequest(BaseModel):
    source:     str           # "abs" | "youtube" | "radio" | "nas"
    uri:        str
    output:     str = "jack"
    start_time: float = 0.0
    title:      str = ""
    author:     str = ""
    cover_url:  str = ""
    http_token: str = ""
    item_id:    str = ""      # ID ABS pour la sync progression
    duration:   float = 0.0


class SeekRequest(BaseModel):
    position: float

class EQRequest(BaseModel):
    bands: list

class SpeedRequest(BaseModel):
    speed: float = 1.0  # 7 valeurs en dB : [60Hz, 150Hz, 400Hz, 1kHz, 2.5kHz, 6kHz, 15kHz]


def _uri_autorisee(uri: str) -> bool:
    """Une adresse web, un fichier du NAS, ou un montage de livre ABS. Rien d'autre."""
    if uri.startswith("edl://"):
        try:
            parts = montage.adresses(uri)
        except ValueError:
            return False
        base = _base_abs()
        return bool(base) and all(a.startswith(base + "/") for a in parts)
    if uri.startswith("http://") or uri.startswith("https://"):
        return True
    return uri.startswith("/") and _is_safe_path(uri)


def _base_abs() -> str:
    return str(load_config().get("abs_url", "")).rstrip("/")


def _jeton_abs(uri: str) -> str:
    """La clé Audiobookshelf, seulement si TOUT ce qui sera lu est sur ton serveur ABS."""
    base = _base_abs()
    if not base:
        return ""
    try:
        parts = montage.adresses(uri)
    except ValueError:
        return ""
    if all(a.startswith(base + "/") for a in parts):
        return load_config().get("abs_api_key", "")
    return ""


@router.post("/play")
async def play(req: PlayRequest):
    global _current_item_id
    if not req.uri:
        raise HTTPException(status_code=400, detail="URI manquante")
    if not _uri_autorisee(req.uri):
        raise HTTPException(status_code=400, detail="Adresse de lecture non autorisée")
    # La clé n'est plus envoyée par l'écran : le serveur l'ajoute, et seulement vers ABS.
    jeton = _jeton_abs(req.uri) if req.source == "abs" else ""
    try:
        # La vitesse choisie reste pour les livres et podcasts ; une radio joue à 1×.
        vitesse = audio.vitesse if req.source in ("abs", "podcast") else 1.0
        await audio.play(req.uri, req.output, req.start_time, jeton, vitesse)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Erreur lecture: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lecture: {str(e)}")

    # Démarrer la sync ABS si c'est un livre audio
    logger.info(f"Play request: source={req.source} item_id='{req.item_id}' start={req.start_time}")
    abs_sync.stop_sync()
    if req.source == "abs" and req.item_id:
        _current_item_id = req.item_id
        abs_sync.start_sync(req.item_id, audio, start_position=req.start_time)
        logger.info(f"Sync ABS démarrée pour item {req.item_id} depuis {req.start_time:.1f}s")
    else:
        _current_item_id = None

    en_cours.clear()
    en_cours.update({"source": req.source, "uri": req.uri, "title": req.title,
                     "author": req.author, "cover_url": req.cover_url,
                     "item_id": req.item_id, "output": req.output})
    await ws_mgr.broadcast({"event": "play", "uri": req.uri,
                             "title": req.title, "author": req.author})
    asyncio.create_task(webhooks.fire("play", {
        "title": req.title, "author": req.author, "source": req.source
    }))
    return {"status": "playing", "uri": req.uri}


@router.post("/pause")
async def pause():
    try:
        await audio.pause()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    # Envoyer la position finale et ARRÊTER la sync
    if _current_item_id:
        try:
            state = await audio.get_status()
            pos = state.get("position", 0)
            dur = state.get("duration", 0)
            # Envoyer la position finale
            await abs_sync._send_progress(_current_item_id, pos, dur)
            logger.info(f"Position finale à la pause: {pos:.1f}s")
        except Exception as e:
            logger.debug(f"Sync pause: {e}")
        # ARRÊTER la sync — ne plus rien envoyer jusqu'au prochain play
        abs_sync.stop_sync()
    await ws_mgr.broadcast({"event": "pause"})
    asyncio.create_task(webhooks.fire("pause", {}))
    return {"status": "paused"}


@router.post("/resume")
async def resume():
    try:
        await audio.resume()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    # La pause arrête l'envoi de la position à ABS : il faut le relancer ici.
    # Avant, après pause + reprise, plus rien n'était enregistré dans ABS.
    if _current_item_id:
        abs_sync.start_sync(_current_item_id, audio, attente=2)
    await ws_mgr.broadcast({"event": "resume"})
    return {"status": "playing"}


@router.post("/stop")
async def stop():
    global _current_item_id
    # La position finale part AVANT d'arrêter mpv : après, il ne la connaît plus.
    if _current_item_id:
        try:
            state = await audio.get_status()
            await abs_sync._send_progress(_current_item_id, state.get("position", 0), state.get("duration", 0))
        except Exception as e:
            logger.debug(f"Sync stop: {e}")
    abs_sync.stop_sync()
    _current_item_id = None
    # Puis arrêter mpv
    await audio.stop()
    await ws_mgr.broadcast({"event": "stop"})
    logger.info("Lecture arrêtée — sync ABS stoppée")
    asyncio.create_task(webhooks.fire("stop", {}))
    return {"status": "stopped"}


@router.post("/seek")
async def seek(req: SeekRequest):
    if req.position < 0:
        raise HTTPException(status_code=400, detail="Position négative")
    await audio.seek(req.position)
    return {"status": "seeked", "position": req.position}


@router.post("/volume/{level}")
async def set_volume(level: int):
    if not 0 <= level <= 100:
        raise HTTPException(status_code=400, detail="Volume entre 0 et 100")
    await audio.set_volume(level)
    return {"volume": level}


# ── Minuterie de sommeil ─────────────────────────────────────────────────────
# Elle tourne sur la box : avant, elle vivait dans la page et s'arrêtait si
# l'écran ou le téléphone qui l'avait lancée se mettait en veille.
_sommeil: asyncio.Task | None = None
_sommeil_fin: float = 0.0


class SommeilRequest(BaseModel):
    minutes: int = 0   # 0 = annuler


async def _dormir(secondes: float):
    global _sommeil_fin
    try:
        attente = max(0.0, secondes - 30)
        await asyncio.sleep(attente)
        # 30 dernières secondes : le son baisse doucement au lieu de couper net.
        depart = audio._volume
        for i in range(30):
            await audio.set_volume(max(0, int(depart * (29 - i) / 30)))
            await asyncio.sleep(1)
        await stop()
        await audio.set_volume(depart)
        await ws_mgr.broadcast({"event": "sleep_done"})
    except asyncio.CancelledError:
        pass
    finally:
        _sommeil_fin = 0.0


@router.post("/sleep")
async def minuterie(req: SommeilRequest):
    global _sommeil, _sommeil_fin
    if _sommeil and not _sommeil.done():
        _sommeil.cancel()
    _sommeil_fin = 0.0
    if req.minutes > 0:
        _sommeil_fin = time.time() + req.minutes * 60
        _sommeil = asyncio.create_task(_dormir(req.minutes * 60))
    return {"minutes": req.minutes, "reste": sommeil_reste()}


def sommeil_reste() -> int:
    return max(0, int(_sommeil_fin - time.time())) if _sommeil_fin else 0


@router.post("/speed")
async def set_speed(req: SpeedRequest):
    """Règle la vitesse de lecture."""
    speed = max(0.25, min(4.0, req.speed))
    await audio.set_speed(speed)
    return {"status": "ok", "speed": speed}


@router.post("/equalizer")
async def set_equalizer(req: EQRequest):
    """Applique l'égaliseur à mpv via filtre lavfi."""
    try:
        if len(req.bands) != 7:
            raise HTTPException(status_code=400, detail="7 bandes requises")

        # Construire le filtre equalizer pour ffmpeg/mpv
        freqs = [60, 150, 400, 1000, 2500, 6000, 15000]
        filters = []
        for i, (freq, gain) in enumerate(zip(freqs, req.bands)):
            if gain != 0:
                filters.append(f"equalizer=f={freq}:width_type=o:width=2:g={gain}")

        if filters:
            af = ",".join(filters)
        else:
            af = "anull"

        # Appliquer via mpv IPC
        await audio.set_equalizer(af)

        # Sauvegarder pour la prochaine lecture
        audio._eq_filter = af
        return {"status": "applied", "filter": af}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _etat_complet(state: dict) -> dict:
    """L'état du lecteur, plus la minuterie, la vitesse et ce qui joue."""
    state["sommeil"] = sommeil_reste()
    state["vitesse"] = audio.vitesse
    state["item_id"] = _current_item_id
    if state.get("stopped"):
        state.update({"source": "", "title": "", "author": "", "cover_url": ""})
    else:
        for k in ("source", "title", "author", "cover_url"):
            state[k] = en_cours.get(k, "")
    return state


@router.get("/status")
async def status():
    try:
        return _etat_complet(await audio.get_status())
    except Exception as e:
        logger.error(f"Erreur status: {e}")
        return {"playing": False, "paused": False, "stopped": True,
                "uri": "", "position": 0, "duration": 0, "volume": 80, "progress": 0}


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws_mgr.connect(ws)
    try:
        while True:
            try:
                state = _etat_complet(await audio.get_status())
                await ws.send_json(state)
            except Exception:
                break
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass
    finally:
        ws_mgr.disconnect(ws)
