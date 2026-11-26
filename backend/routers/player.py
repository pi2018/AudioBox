import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
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

# Livre Audiobookshelf en cours (pour lui envoyer la progression)
_current_item_id = None
# Ce qui joue (titre, auteur, pochette, source…) : pour l'écran, l'appli et Home Assistant.
# Gardé après l'arrêt, avec la position : « Lecture » peut alors reprendre la dernière écoute.
en_cours: dict = {}

# Sources reprises à leur position (une radio repart toujours du direct).
REPRISE_A_LA_POSITION = ("abs", "podcast", "nas", "youtube")


class PlayRequest(BaseModel):
    source:     str           # "abs" | "youtube" | "radio" | "nas" | "podcast" | "url"
    uri:        str
    output:     str = "jack"
    start_time: float = 0.0
    title:      str = ""
    author:     str = ""
    cover_url:  str = ""
    http_token: str = ""      # ignoré : la clé ABS est ajoutée par le serveur
    item_id:    str = ""      # ID ABS pour la sync progression
    duration:   float = 0.0
    page:       str = ""      # YouTube : la page de la vidéo (son adresse de lecture expire)


class SeekRequest(BaseModel):
    position: float

class EQRequest(BaseModel):
    bands: list  # 7 valeurs en dB : [60Hz, 150Hz, 400Hz, 1kHz, 2.5kHz, 6kHz, 15kHz]

class SpeedRequest(BaseModel):
    speed: float = 1.0


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


async def _cloturer_livre(garder_item: bool = False):
    """
    Envoie à Audiobookshelf la position du livre en cours, puis arrête la synchro.
    Toujours AVANT de changer ce qui joue : avant (1.5), en passant directement d'un
    livre à un autre, la position du nouveau était enregistrée dans l'ancien.
    """
    global _current_item_id
    if _current_item_id:
        await abs_sync.envoyer_position_finale(_current_item_id, audio)
    abs_sync.stop_sync()
    if not garder_item:
        _current_item_id = None


async def lancer(req: PlayRequest, en_pause: bool = False) -> dict:
    """Démarre une lecture : écran, appli, Home Assistant, reprise après une annonce…"""
    global _current_item_id
    if not req.uri:
        raise HTTPException(status_code=400, detail="URI manquante")
    if not _uri_autorisee(req.uri):
        raise HTTPException(status_code=400, detail="Adresse de lecture non autorisée")
    await _cloturer_livre()
    # La clé n'est plus envoyée par l'écran : le serveur l'ajoute, et seulement vers ABS.
    jeton = _jeton_abs(req.uri) if req.source == "abs" else ""
    try:
        # La vitesse choisie reste pour les livres et podcasts ; une radio joue à 1×.
        vitesse = audio.vitesse if req.source in ("abs", "podcast") else 1.0
        await audio.play(req.uri, req.output, req.start_time, jeton, vitesse, en_pause)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Erreur lecture: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lecture: {str(e)}")

    logger.info(f"Lecture : source={req.source} item_id='{req.item_id}' start={req.start_time:.1f}")
    if req.source == "abs" and req.item_id:
        _current_item_id = req.item_id
        abs_sync.start_sync(req.item_id, audio, start_position=req.start_time)

    en_cours.clear()
    en_cours.update({"source": req.source, "uri": req.uri, "title": req.title,
                     "author": req.author, "cover_url": req.cover_url, "item_id": req.item_id,
                     "output": req.output, "position": req.start_time, "page": req.page})
    await ws_mgr.broadcast({"event": "play", "uri": req.uri,
                             "title": req.title, "author": req.author})
    webhooks.lancer(webhooks.fire("play", {
        "title": req.title, "author": req.author, "source": req.source
    }))
    return {"status": "paused" if en_pause else "playing", "uri": req.uri}


@router.post("/play")
async def play(req: PlayRequest):
    return await lancer(req)


async def reprendre() -> dict:
    """Après un arrêt : relance la dernière écoute (un livre à sa position ABS, une radio en direct)."""
    dernier = dict(en_cours)
    if not dernier.get("uri"):
        raise HTTPException(status_code=409, detail="Rien à reprendre : choisis d'abord quoi écouter")
    source = dernier.get("source", "")
    uri = dernier["uri"]
    depart = 0.0
    if source in REPRISE_A_LA_POSITION:
        depart = float(dernier.get("position") or 0)
    if source == "abs" and dernier.get("item_id"):
        serveur = await abs_sync.get_server_position(dernier["item_id"])
        if serveur > 0:
            depart = serveur
    if source == "youtube" and dernier.get("page"):
        # L'adresse de lecture YouTube expire au bout de quelques heures : on la redemande.
        from routers.youtube import resolve, YoutubeRequest
        try:
            uri = (await resolve(YoutubeRequest(url=dernier["page"]))).get("url") or uri
        except HTTPException:
            pass
    return await lancer(PlayRequest(
        source=source, uri=uri, output=dernier.get("output", "jack"), start_time=depart,
        title=dernier.get("title", ""), author=dernier.get("author", ""),
        cover_url=dernier.get("cover_url", ""), item_id=dernier.get("item_id", ""),
        page=dernier.get("page", "")))


@router.post("/pause")
async def pause():
    try:
        await audio.pause()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    # La position part tout de suite ; la synchro reprend avec la lecture.
    await _cloturer_livre(garder_item=True)
    await ws_mgr.broadcast({"event": "pause"})
    webhooks.lancer(webhooks.fire("pause", {}))
    return {"status": "paused"}


@router.post("/resume")
async def resume():
    st = await audio.get_status()
    if st.get("stopped"):
        # Rien de chargé : on reprend la dernière écoute (bouton Lecture de l'écran,
        # de l'appli ou de Home Assistant). Avant, il ne se passait rien.
        return await reprendre()
    try:
        await audio.resume()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    # La pause arrête l'envoi de la position à ABS : il faut le relancer ici.
    if _current_item_id:
        abs_sync.start_sync(_current_item_id, audio, attente=2)
    await ws_mgr.broadcast({"event": "resume"})
    return {"status": "playing"}


@router.post("/stop")
async def stop():
    # La position finale part AVANT d'arrêter mpv : après, il ne la connaît plus.
    try:
        st = await audio.get_status()
        if not st.get("stopped") and en_cours and st.get("position"):
            en_cours["position"] = st["position"]
    except Exception:
        pass
    await _cloturer_livre()
    await audio.stop()
    await ws_mgr.broadcast({"event": "stop"})
    logger.info("Lecture arrêtée — sync ABS stoppée")
    webhooks.lancer(webhooks.fire("stop", {}))
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
BAISSE = 30    # dernières secondes : le son baisse doucement au lieu de couper net
PAS = 1.0      # une marche par seconde


class SommeilRequest(BaseModel):
    minutes: int = 0   # 0 = annuler


async def _dormir(secondes: float):
    global _sommeil_fin
    depart = None
    try:
        await asyncio.sleep(max(0.0, secondes - BAISSE * PAS))
        depart = audio._volume
        for i in range(BAISSE):
            await audio.set_volume(max(0, int(depart * (BAISSE - 1 - i) / BAISSE)))
            await asyncio.sleep(PAS)
        await stop()
        await ws_mgr.broadcast({"event": "sleep_done"})
    except asyncio.CancelledError:
        pass
    finally:
        # Le volume revient comme avant, même si on annule pendant que le son baisse
        # (avant : il restait bas).
        if depart is not None:
            await audio.set_volume(depart)
        # Seulement si c'est encore LA minuterie en cours. Avant (1.5), l'ancienne,
        # annulée en en choisissant une nouvelle, effaçait le temps de la nouvelle :
        # l'écran n'affichait plus rien, mais la musique s'arrêtait quand même.
        if _sommeil is asyncio.current_task():
            _sommeil_fin = 0.0


@router.post("/sleep")
async def minuterie(req: SommeilRequest):
    global _sommeil, _sommeil_fin
    minutes = max(0, min(int(req.minutes), 24 * 60))
    ancienne = _sommeil
    _sommeil, _sommeil_fin = None, 0.0
    if ancienne and not ancienne.done():
        ancienne.cancel()
    if minutes > 0:
        _sommeil_fin = time.time() + minutes * 60
        _sommeil = asyncio.create_task(_dormir(minutes * 60))
    return {"minutes": minutes, "reste": sommeil_reste()}


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
        for freq, gain in zip(freqs, req.bands):
            gain = max(-12.0, min(12.0, float(gain)))
            if gain != 0:
                filters.append(f"equalizer=f={freq}:width_type=o:width=2:g={gain:g}")

        af = ",".join(filters) if filters else "anull"
        # Appliquer via mpv IPC, et garder pour la prochaine lecture
        await audio.set_equalizer(af)
        return {"status": "applied", "filter": af}
    except HTTPException:
        raise
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Valeurs d'égaliseur invalides")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _etat_complet(state: dict) -> dict:
    """L'état du lecteur, plus la minuterie, la vitesse et ce qui joue."""
    state["sommeil"] = sommeil_reste()
    state["vitesse"] = audio.vitesse
    state["item_id"] = _current_item_id
    if state.get("stopped"):
        state.update({"source": "", "title": "", "author": "", "cover_url": ""})
        # Ce que le bouton Lecture relancerait (pour l'appli et Home Assistant).
        state["dernier"] = en_cours.get("title", "") if en_cours.get("uri") else ""
    else:
        for k in ("source", "title", "author", "cover_url"):
            state[k] = en_cours.get(k, "")
        state["dernier"] = ""
        if state.get("position") and en_cours:
            en_cours["position"] = state["position"]
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
