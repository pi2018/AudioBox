"""Petit client pour l'API de la box AudioBox (aucune dépendance en plus)."""
from __future__ import annotations

from urllib.parse import quote

import aiohttp


class AudioBoxErreur(Exception):
    """La box ne répond pas, ou refuse le code."""


class AudioBoxApi:
    def __init__(self, session: aiohttp.ClientSession, hote: str, port: int, token: str) -> None:
        self._session = session
        self.base = f"http://{hote}:{port}"
        self._entetes = {"Authorization": f"Bearer {token}"} if token else {}

    async def _appel(self, methode: str, chemin: str, json: dict | None = None,
                     delai: float = 15) -> dict:
        try:
            async with self._session.request(
                methode, self.base + chemin, json=json, headers=self._entetes,
                timeout=aiohttp.ClientTimeout(total=delai),
            ) as r:
                if r.status == 401:
                    raise AudioBoxErreur("code refusé")
                if r.status >= 400:
                    # Le message de la box (« Rien à reprendre… »), pas seulement le code.
                    try:
                        corps = await r.json(content_type=None)
                    except ValueError:
                        corps = None
                    detail = corps.get("detail") if isinstance(corps, dict) else None
                    raise AudioBoxErreur(str(detail or f"erreur {r.status}"))
                return await r.json(content_type=None) or {}
        except aiohttp.ClientError as err:
            raise AudioBoxErreur(str(err)) from err
        except TimeoutError as err:
            raise AudioBoxErreur("pas de réponse") from err

    async def etat(self) -> dict:
        return await self._appel("GET", "/api/public/state")

    async def verifier_code(self) -> None:
        """Le code n'est utile que pour les annonces : on le vérifie sur une route protégée."""
        await self._appel("GET", "/api/settings/")

    async def lecture(self) -> None:
        await self._appel("POST", "/api/public/play")

    async def pause(self) -> None:
        await self._appel("POST", "/api/public/pause")

    async def stop(self) -> None:
        await self._appel("POST", "/api/public/stop")

    async def volume(self, niveau: int) -> None:
        await self._appel("POST", f"/api/public/volume/{max(0, min(100, niveau))}")

    async def aller_a(self, secondes: float) -> None:
        await self._appel("POST", f"/api/public/seek/{max(0.0, secondes)}")

    async def suivant(self) -> None:
        await self._appel("POST", "/api/public/suivant")

    async def precedent(self) -> None:
        await self._appel("POST", "/api/public/precedent")

    async def radio(self, nom: str) -> None:
        await self._appel("POST", f"/api/public/radio/{quote(nom, safe='')}")

    async def lire_adresse(self, url: str, titre: str = "") -> None:
        await self._appel("POST", "/api/public/play_url", {"url": url, "title": titre})

    async def annonce(self, url: str) -> None:
        # La box répond quand le message est fini (et la musique reprise) : jusqu'à 5 min.
        await self._appel("POST", "/api/public/annonce", {"url": url}, delai=330)

    async def minuterie(self, minutes: int) -> None:
        await self._appel("POST", "/api/player/sleep", {"minutes": minutes})
