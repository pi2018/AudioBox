"""
Synchronisation de la progression de lecture vers Audiobookshelf.
"""
import asyncio, logging
import httpx
from config import load_config
# Import différé pour éviter les imports circulaires
_webhooks = None

def _get_webhooks():
    global _webhooks
    if _webhooks is None:
        try:
            from services import webhooks
            _webhooks = webhooks
        except Exception:
            pass
    return _webhooks

logger = logging.getLogger("abs_sync")

_sync_task = None


async def get_server_position(item_id: str) -> float:
    """Récupère TOUJOURS la position depuis ABS — source de vérité unique."""
    cfg = load_config()
    abs_url = str(cfg.get("abs_url", "")).rstrip("/")
    api_key = cfg.get("abs_api_key", "")
    if not abs_url or not api_key:
        return 0.0
    try:
        async with httpx.AsyncClient(
            base_url=abs_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=5.0
        ) as c:
            # Essayer avec libraryItemId
            r = await c.get(f"/api/me/progress/{item_id}")
            if r.status_code == 200:
                data = r.json()
                pos = data.get("currentTime", 0)
                logger.info(f"Position ABS récupérée: {pos:.1f}s pour {item_id}")
                return float(pos)

            # Fallback: chercher dans /api/me
            r2 = await c.get("/api/me")
            if r2.status_code == 200:
                for prog in r2.json().get("mediaProgress", []):
                    if prog.get("libraryItemId") == item_id:
                        pos = prog.get("currentTime", 0)
                        logger.info(f"Position ABS (fallback): {pos:.1f}s")
                        return float(pos)
    except Exception as e:
        logger.warning(f"Impossible de récupérer position ABS: {e}")
    return 0.0


async def _send_progress(item_id: str, position: float,
                         duration: float, is_finished: bool = False):
    """Envoie la progression vers ABS."""
    cfg = load_config()
    abs_url = str(cfg.get("abs_url", "")).rstrip("/")
    api_key = cfg.get("abs_api_key", "")
    if not abs_url or not api_key or not item_id or position <= 0:
        return
    try:
        progress = round(position / duration, 4) if duration > 0 else 0
        payload = {
            "currentTime": round(position, 1),
            "duration":    round(duration, 1),
            "progress":    progress,
            "isFinished":  is_finished,
        }
        async with httpx.AsyncClient(
            base_url=abs_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=5.0
        ) as c:
            await c.patch(f"/api/me/progress/{item_id}", json=payload)
        logger.info(f"Sync ABS envoyée: {item_id} position={position:.1f}s")
    except Exception as e:
        logger.warning(f"Sync ABS échouée: {e}")


async def _sync_loop(item_id: str, audio_manager):
    logger.info(f"Sync ABS démarrée pour item {item_id}")
    # Attendre que mpv soit bien positionné
    await asyncio.sleep(8)
    last_sent = -1

    while True:
        try:
            await asyncio.sleep(5)
            state    = await audio_manager.get_status()
            position = state.get("position", 0)
            duration = state.get("duration", 0)

            if not state.get("playing") and not state.get("paused"):
                logger.info(f"Lecture terminée pour {item_id}")
                wh = _get_webhooks()
                if wh:
                    asyncio.create_task(wh.fire("finished", {"item_id": item_id}))
                break

            # Envoyer seulement si position a avancé d'au moins 1s
            if position > last_sent + 1:
                await _send_progress(item_id, position, duration)
                last_sent = position

        except asyncio.CancelledError:
            try:
                state = await audio_manager.get_status()
                pos = state.get("position", 0)
                if pos > 0:
                    await _send_progress(item_id, pos, state.get("duration", 0))
                    logger.info(f"Position finale envoyée: {pos:.1f}s")
            except Exception:
                pass
            break
        except Exception as e:
            logger.error(f"Erreur sync: {e}")
            await asyncio.sleep(5)


def start_sync(item_id: str, audio_manager, start_position: float = 0.0):
    global _sync_task
    stop_sync()
    _sync_task = asyncio.create_task(_sync_loop(item_id, audio_manager))


def stop_sync():
    global _sync_task
    if _sync_task and not _sync_task.done():
        _sync_task.cancel()
    _sync_task = None
