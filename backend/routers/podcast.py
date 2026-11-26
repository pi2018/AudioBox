"""
Lecture des flux RSS de podcasts (et des listes de radios OPML), par la box elle-même.

Avant, l'écran passait par un service public (api.allorigins.win) : souvent en
panne, et qui voyait passer la liste de tes podcasts. Maintenant c'est la box
qui télécharge le flux et le rend à l'écran. Elle refuse toute adresse qui mène à
elle-même (voir services/reseau.py).
"""
from fastapi import APIRouter, HTTPException
import logging

from services import reseau

router = APIRouter(prefix="/podcast", tags=["podcast"])
logger = logging.getLogger("podcast")

TAILLE_MAX = 5 * 1024 * 1024  # un flux RSS de plus de 5 Mo n'est pas normal


@router.get("/rss")
async def lire_rss(url: str):
    try:
        return {"contents": await reseau.telecharger_texte(url, TAILLE_MAX)}
    except reseau.AdresseRefusee as e:
        raise HTTPException(status_code=400, detail=str(e))
    except reseau.TelechargementEchoue as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.warning(f"Flux illisible {url[:120]}: {e}")
        raise HTTPException(status_code=502, detail="Flux injoignable")
