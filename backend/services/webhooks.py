"""
Service de webhooks — notifie des URLs externes sur les événements AudioBox.
"""
import httpx, asyncio, logging
from config import load_config

logger = logging.getLogger("webhooks")


async def fire(event: str, data: dict = {}):
    """Envoie le webhook à toutes les URLs configurées pour cet événement."""
    config   = load_config()
    webhooks = config.get("webhooks", [])
    if not webhooks:
        return

    payload = {"event": event, "data": data}

    for wh in webhooks:
        url    = wh.get("url", "")
        events = wh.get("events", [])
        if not url:
            continue
        if events and event not in events:
            continue
        asyncio.create_task(_send(url, payload))


async def _send(url: str, payload: dict):
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            await c.post(url, json=payload)
            logger.info(f"Webhook envoyé: {url} event={payload['event']}")
    except Exception as e:
        logger.warning(f"Webhook échoué {url}: {e}")
