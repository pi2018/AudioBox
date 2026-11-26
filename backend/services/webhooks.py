"""
Service de webhooks — notifie des URLs externes sur les événements AudioBox.
"""
import httpx, asyncio, logging
from config import load_config

logger = logging.getLogger("webhooks")

# Les envois en cours. Python ne garde qu'une référence faible vers une tâche lancée
# avec create_task : sans cette liste, un envoi pouvait disparaître en route.
_en_cours: set[asyncio.Task] = set()


def lancer(coro) -> asyncio.Task:
    """Lance une tâche de fond en la gardant en vie jusqu'au bout."""
    tache = asyncio.create_task(coro)
    _en_cours.add(tache)
    tache.add_done_callback(_en_cours.discard)
    return tache


async def fire(event: str, data: dict | None = None):
    """Envoie le webhook à toutes les URLs configurées pour cet événement."""
    config   = load_config()
    webhooks = config.get("webhooks", [])
    if not webhooks:
        return

    payload = {"event": event, "data": data or {}}

    for wh in webhooks:
        url    = wh.get("url", "")
        events = wh.get("events", [])
        if not url:
            continue
        if events and event not in events:
            continue
        lancer(_send(url, payload))


async def _send(url: str, payload: dict):
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            await c.post(url, json=payload)
            logger.info(f"Webhook envoyé: {url} event={payload['event']}")
    except Exception as e:
        logger.warning(f"Webhook échoué {url}: {e}")
