from fastapi import APIRouter, HTTPException
import httpx, logging
from config import load_config

router = APIRouter(prefix="/abs", tags=["audiobookshelf"])
logger = logging.getLogger("abs")


def _client() -> httpx.AsyncClient:
    cfg = load_config()
    if not cfg.get("abs_url"):
        raise HTTPException(status_code=503,
            detail="Audiobookshelf non configuré — allez dans Paramètres > Audiobookshelf")
    if not cfg.get("abs_api_key"):
        raise HTTPException(status_code=503,
            detail="Clé API Audiobookshelf manquante — allez dans Paramètres > Audiobookshelf")
    return httpx.AsyncClient(
        base_url=str(cfg["abs_url"]).rstrip("/"),
        headers={"Authorization": f"Bearer {cfg['abs_api_key']}"},
        timeout=10.0,
        follow_redirects=True
    )


async def _abs_get(path: str, params: dict = None):
    try:
        async with _client() as c:
            r = await c.get(path, params=params)

            if r.status_code == 401:
                raise HTTPException(status_code=401,
                    detail="Clé API Audiobookshelf invalide ou expirée")
            if r.status_code == 404:
                raise HTTPException(status_code=404,
                    detail=f"Ressource ABS introuvable: {path}")

            # Vérifier que la réponse est bien du JSON
            content_type = r.headers.get("content-type", "")
            if r.status_code != 200:
                raise HTTPException(status_code=r.status_code,
                    detail=f"ABS a répondu {r.status_code}: {r.text[:200]}")

            if not r.content:
                raise HTTPException(status_code=502,
                    detail="ABS a renvoyé une réponse vide")

            if "application/json" not in content_type and "text/json" not in content_type:
                # Essayer quand même de parser
                try:
                    return r.json()
                except Exception:
                    raise HTTPException(status_code=502,
                        detail=f"ABS n'a pas renvoyé du JSON (content-type: {content_type}). Vérifiez l'URL du serveur.")

            return r.json()

    except httpx.ConnectError:
        raise HTTPException(status_code=503,
            detail="Impossible de joindre Audiobookshelf — vérifiez l'URL et que le serveur est démarré")
    except httpx.ConnectTimeout:
        raise HTTPException(status_code=504,
            detail="Timeout de connexion — Audiobookshelf ne répond pas")
    except httpx.ReadTimeout:
        raise HTTPException(status_code=504,
            detail="Timeout — Audiobookshelf met trop de temps à répondre")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ABS erreur inattendue: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur ABS: {str(e)}")


@router.get("/libraries")
async def get_libraries():
    cfg = load_config()
    # ABS pas encore configuré → retourner liste vide au lieu d'une erreur
    if not cfg.get("abs_url") or not cfg.get("abs_api_key"):
        return {"libraries": []}
    return await _abs_get("/api/libraries")


@router.get("/libraries/{lib_id}/items")
async def get_items(lib_id: str, page: int = 0, limit: int = 50):
    return await _abs_get(f"/api/libraries/{lib_id}/items",
                          params={"page": page, "limit": limit})


@router.get("/items/{item_id}")
async def get_item(item_id: str):
    return await _abs_get(f"/api/items/{item_id}")


@router.get("/me/progress/{item_id}")
async def get_progress(item_id: str):
    """Récupère la progression — essaie libraryItemId puis mediaItemId."""
    # Essayer d'abord avec libraryItemId
    try:
        result = await _abs_get(f"/api/me/progress/{item_id}")
        return result
    except HTTPException:
        pass

    # Fallback : récupérer le mediaItemId depuis l'item puis reessayer
    try:
        item = await _abs_get(f"/api/items/{item_id}")
        media_item_id = item.get("media", {}).get("id", "")
        if media_item_id and media_item_id != item_id:
            return await _abs_get(f"/api/me/progress/{media_item_id}")
    except HTTPException:
        pass

    # Dernier fallback : chercher dans /api/me/items-in-progress
    try:
        me = await _abs_get("/api/me")
        for prog in me.get("mediaProgress", []):
            if prog.get("libraryItemId") == item_id:
                return prog
    except Exception:
        pass

    raise HTTPException(status_code=404, detail=f"Progression introuvable pour {item_id}")


@router.patch("/me/progress/{item_id}")
async def sync_progress(item_id: str, payload: dict):
    try:
        async with _client() as c:
            r = await c.patch(f"/api/me/progress/{item_id}", json=payload)
            if r.status_code == 401:
                raise HTTPException(status_code=401, detail="Clé API invalide")
            r.raise_for_status()
            if not r.content:
                return {"status": "ok"}
            return r.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Audiobookshelf injoignable")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/me")
async def get_me():
    """Récupère le profil utilisateur avec toute la progression."""
    return await _abs_get("/api/me")


@router.get("/search")
async def search(q: str, lib_id: str = ""):
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="Requête vide")
    params = {"q": q.strip()}
    if lib_id:
        params["library"] = lib_id
    return await _abs_get("/api/search", params=params)


@router.get("/cover/{item_id}")
async def get_cover(item_id: str):
    """Proxy la pochette depuis ABS vers le frontend."""
    from fastapi.responses import Response, RedirectResponse
    try:
        async with _client() as c:
            r = await c.get(f"/api/items/{item_id}/cover",
                            params={"width": 300, "height": 300, "format": "jpeg"})
            if r.status_code == 200:
                return Response(
                    content=r.content,
                    media_type=r.headers.get("content-type", "image/jpeg")
                )
            # Fallback : rediriger vers ABS directement
            cfg = load_config()
            return RedirectResponse(
                url=f"{str(cfg['abs_url']).rstrip('/')}/api/items/{item_id}/cover"
            )
    except Exception:
        # Retourner une image transparente 1x1 en cas d'erreur
        import base64
        px = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
        )
        return Response(content=px, media_type="image/png")


@router.get("/position/{item_id}")
async def get_position(item_id: str):
    """Retourne TOUJOURS la position exacte depuis ABS — source de vérité unique."""
    from services.abs_sync import get_server_position
    position = await get_server_position(item_id)
    return {"item_id": item_id, "position": position}


@router.get("/stream/{item_id}")
async def stream_item(item_id: str, file_id: str = ""):
    """Retourne l'URL de stream directe avec token pour mpv."""
    cfg = load_config()
    abs_url = str(cfg.get("abs_url", "")).rstrip("/")
    api_key = cfg.get("abs_api_key", "")

    if not abs_url or not api_key:
        raise HTTPException(status_code=503, detail="ABS non configuré")

    try:
        async with _client() as c:
            r = await c.get(f"/api/items/{item_id}")
            r.raise_for_status()
            item = r.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur récupération item: {str(e)}")

    logger.info(f"Stream item keys: {list(item.get('media', {}).keys())}")

    media = item.get("media", {})
    duration = media.get("duration", 0)
    title = media.get("metadata", {}).get("title", "")

    # Chercher les fichiers audio dans tous les champs possibles
    files = (media.get("audioFiles")
          or media.get("tracks")
          or media.get("audioFile")
          or [])

    # Cas livre audio avec un seul fichier
    if isinstance(files, dict):
        files = [files]

    logger.info(f"Stream: {len(files)} fichier(s) trouvé(s) pour item {item_id}")

    if files:
        f = files[0]
        if file_id:
            f = next((x for x in files if str(x.get("ino","")) == file_id), files[0])
        ino = f.get("ino", f.get("id", ""))
        stream_url = f"{abs_url}/api/items/{item_id}/file/{ino}"
    else:
        # Fallback : stream direct via l'API ABS
        stream_url = f"{abs_url}/api/items/{item_id}/stream"
        logger.warning(f"Aucun audioFile trouvé, utilisation du stream direct")

    return {
        "url":      stream_url,
        "token":    api_key,
        "title":    title,
        "duration": duration,
        "item_id":  item_id,
    }
