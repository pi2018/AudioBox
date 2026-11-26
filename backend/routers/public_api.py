"""
API REST publique AudioBox — sans code, pour Home Assistant, l'appli du téléphone et
les scripts : état, lecture, pause, volume, radios. Ce qui fait télécharger une adresse
à la box (lire une adresse, faire une annonce) demande le code admin.
"""
import asyncio
import logging
import time
import unicodedata

import httpx

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from config import load_config
# Lecture, pause et arrêt passent par les fonctions du lecteur : sinon l'envoi de la
# position à Audiobookshelf n'était pas suivi.
from routers import abs as absr
from routers import player as lecteur
from routers.player import audio, ws_mgr
from routers.settings import verify_token
from config import update_config
from services import abs_sync

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


# ── Pour l'appli du téléphone : livres et radios ─────────────────────────────

_cache_livres: dict = {"quand": 0.0, "livres": []}
DUREE_CACHE = 60.0


def _livre_vu_par_l_appli(item: dict, prog: dict | None) -> dict:
    m = (item.get("media") or {}).get("metadata") or {}
    prog = prog or {}
    return {
        "id": item.get("id", ""),
        "titre": m.get("title") or "Sans titre",
        "auteur": m.get("authorName") or "",
        "duree": float((item.get("media") or {}).get("duration") or 0),
        "progression": float(prog.get("progress") or 0),
        "termine": bool(prog.get("isFinished")),
        "maj": float(prog.get("lastUpdate") or 0),
    }


async def _tous_les_livres(forcer: bool = False) -> list[dict]:
    """Tous les livres des bibliothèques Audiobookshelf, avec ta progression (gardés 1 min)."""
    if not forcer and time.monotonic() - _cache_livres["quand"] < DUREE_CACHE and _cache_livres["livres"]:
        return _cache_livres["livres"]
    cfg = load_config()
    if not cfg.get("abs_url") or not cfg.get("abs_api_key"):
        return []
    libs = (await absr._abs_get("/api/libraries")).get("libraries", [])
    libs = [b for b in libs if b.get("mediaType", "book") == "book"] or libs
    me = await absr._abs_get("/api/me")
    progres = {p.get("libraryItemId"): p for p in (me.get("mediaProgress", []) if isinstance(me, dict) else [])}
    livres, vus = [], set()
    for lib in libs:
        page = 0
        while page < 20:
            res = await absr._abs_get(f"/api/libraries/{lib['id']}/items",
                                      params={"limit": 200, "page": page, "sort": "media.metadata.title"})
            items = res.get("results", []) if isinstance(res, dict) else []
            for it in items:
                if it.get("id") and it["id"] not in vus:
                    vus.add(it["id"])
                    livres.append(_livre_vu_par_l_appli(it, progres.get(it["id"])))
            if len(items) < 200:
                break
            page += 1
    _cache_livres.update({"quand": time.monotonic(), "livres": livres})
    return livres


def _simple(texte: str) -> str:
    """Minuscules sans accents : « miser » trouve « Les Misérables »."""
    return "".join(c for c in unicodedata.normalize("NFD", texte.lower())
                   if unicodedata.category(c) != "Mn").strip()


@router.get("/livres")
async def liste_livres(q: str = "", rafraichir: bool = False):
    """Les livres (avec recherche) et ceux en cours d'écoute, pour l'appli."""
    livres = await _tous_les_livres(rafraichir)
    cherche = _simple(q)
    if cherche:
        livres = [x for x in livres if cherche in _simple(x["titre"]) or cherche in _simple(x["auteur"])]
    en_cours = sorted((x for x in livres if x["progression"] > 0.01 and not x["termine"]),
                      key=lambda x: x["maj"], reverse=True)[:10]
    return {"livres": livres[:300], "total": len(livres), "en_cours": [] if cherche else en_cours,
            "configure": bool(load_config().get("abs_url") and load_config().get("abs_api_key"))}


@router.post("/livre/{item_id}")
async def lancer_livre(item_id: str):
    """Lance un livre là où tu l'avais laissé (comme sur l'écran de la box)."""
    flux = await absr.stream_item(item_id)
    try:
        item = await absr.get_item(item_id)
    except HTTPException:
        item = {}
    m = (item.get("media") or {}).get("metadata") or {}
    duree = float(flux.get("duration") or 0)
    debut = await abs_sync.get_server_position(item_id)
    if duree and debut > duree - 10:     # livre fini : on le reprend du début
        debut = 0.0
    await lecteur.lancer(lecteur.PlayRequest(
        source="abs", uri=flux["url"], item_id=item_id, duration=duree,
        title=flux.get("title") or m.get("title", ""), author=m.get("authorName", ""),
        start_time=debut, output=load_config().get("default_output", "jack")))
    _cache_livres["quand"] = 0.0
    return {"status": "playing", "titre": flux.get("title", ""), "position": debut}


@router.get("/livre/{item_id}/chapitres")
async def chapitres(item_id: str):
    return {"chapitres": await absr.get_chapters(item_id)}


@router.get("/radios/recherche")
async def chercher_radios(q: str):
    """Cherche des radios sur Radio Browser (annuaire libre) pour les ajouter."""
    q = q.strip()
    if len(q) < 2:
        raise HTTPException(status_code=400, detail="Tape au moins 2 lettres")
    try:
        async with httpx.AsyncClient(timeout=8.0, headers={"User-Agent": "AudioBox"}) as c:
            r = await c.get("https://de1.api.radio-browser.info/json/stations/search",
                            params={"name": q, "limit": 15, "hidebroken": "true",
                                    "order": "clickcount", "reverse": "true"})
            r.raise_for_status()
            trouvees = r.json()
    except Exception:
        raise HTTPException(status_code=502, detail="L'annuaire des radios ne répond pas")
    sortie, vus = [], set()
    for s in trouvees:
        url = (s.get("url_resolved") or s.get("url") or "").strip()
        nom = (s.get("name") or "").strip()
        if nom and url.startswith(("http://", "https://")) and url not in vus:
            vus.add(url)
            sortie.append({"name": nom[:80], "url": url, "favicon": s.get("favicon") or "",
                           "pays": s.get("country") or ""})
    return {"radios": sortie}


class NouvelleRadio(BaseModel):
    name: str
    url: str
    favicon: str = ""


@router.post("/radios")
async def ajouter_radio(radio: NouvelleRadio):
    """Sans code : une radio ajoutée ne fait rien tant qu'on ne la lance pas, et ne donne accès à aucun secret."""
    nom = "".join(ch for ch in radio.name if ch.isprintable()).strip()[:80]
    if not nom:
        raise HTTPException(status_code=400, detail="Donne un nom à la radio")
    url = _adresse_web(radio.url)
    favicon = radio.favicon.strip() if radio.favicon.strip().startswith(("http://", "https://")) else ""
    radios = [r for r in load_config().get("radios", []) if r.get("name", "").strip().lower() != nom.lower()]
    radios.append({"name": nom, "url": url, "favicon": favicon})
    update_config({"radios": radios})
    return {"status": "ok", "radios": [r["name"] for r in radios]}


@router.delete("/radios/{name:path}")
async def supprimer_radio(name: str):
    avant = load_config().get("radios", [])
    apres = [r for r in avant if r.get("name", "").strip().lower() != name.strip().lower()]
    if len(apres) == len(avant):
        raise HTTPException(status_code=404, detail=f"Radio « {name} » introuvable")
    update_config({"radios": apres})
    return {"status": "ok", "radios": [r["name"] for r in apres]}
