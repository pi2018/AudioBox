"""
Lecture des flux RSS de podcasts, par la box elle-même.

Avant, l'écran passait par un service public (api.allorigins.win) : souvent en
panne, et qui voyait passer la liste de tes podcasts. Maintenant c'est la box
qui télécharge le flux et le rend à l'écran.
"""
from fastapi import APIRouter, HTTPException
import httpx, logging

router = APIRouter(prefix="/podcast", tags=["podcast"])
logger = logging.getLogger("podcast")

TAILLE_MAX = 5 * 1024 * 1024  # un flux RSS de plus de 5 Mo n'est pas normal


@router.get("/rss")
async def lire_rss(url: str):
    if not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(status_code=400, detail="Adresse de flux invalide")
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True,
                                     headers={"User-Agent": "AudioBox/1.4"}) as c:
            async with c.stream("GET", url) as r:
                if r.status_code != 200:
                    raise HTTPException(status_code=502, detail=f"Le flux a répondu {r.status_code}")
                morceaux, taille = [], 0
                async for bout in r.aiter_bytes():
                    taille += len(bout)
                    if taille > TAILLE_MAX:
                        raise HTTPException(status_code=413, detail="Flux trop gros")
                    morceaux.append(bout)
        return {"contents": b"".join(morceaux).decode("utf-8", errors="replace")}
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Flux illisible {url}: {e}")
        raise HTTPException(status_code=502, detail="Flux injoignable")
