from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from pydantic import BaseModel
import asyncio, logging
from services.audio_manager import AudioManager
from services.ws_manager import WSManager
from services import abs_sync, webhooks

router  = APIRouter(prefix="/player", tags=["player"])
audio   = AudioManager()
ws_mgr  = WSManager()
logger  = logging.getLogger("player")

# Session de lecture courante
_current_item_id = None


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


@router.post("/play")
async def play(req: PlayRequest):
    global _current_item_id
    if not req.uri:
        raise HTTPException(status_code=400, detail="URI manquante")
    try:
        await audio.play(req.uri, req.output, req.start_time, req.http_token)
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
    await ws_mgr.broadcast({"event": "resume"})
    return {"status": "playing"}


@router.post("/stop")
async def stop():
    global _current_item_id
    # Arrêter la sync EN PREMIER
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


@router.get("/status")
async def status():
    try:
        return await audio.get_status()
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
                state = await audio.get_status()
                await ws.send_json(state)
            except Exception:
                break
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass
    finally:
        ws_mgr.disconnect(ws)
