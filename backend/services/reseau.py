"""
Téléchargements que la box fait pour l'écran (flux de podcast, liste de radios OPML).

La box fait confiance à ce qui vient d'elle-même (127.0.0.1) : c'est ce qui permet à
l'écran tactile de la régler sans taper le code admin. Elle ne doit donc JAMAIS aller
chercher une adresse sur elle-même pour le compte de quelqu'un d'autre. Avant (1.5),
« télécharge http://127.0.0.1:8000/api/settings/setup-info » donnait le code admin à
n'importe qui sur le réseau, et « …/api/system/backup » la clé Audiobookshelf.

On refuse donc les adresses de la box elle-même (boucle locale, 0.0.0.0, lien local),
avant chaque requête, à chaque redirection, et on revérifie l'adresse réellement jointe.
Les appareils de la maison (NAS, Unraid…) restent permis.
"""
import asyncio
import ipaddress
import re
import socket
from urllib.parse import urljoin, urlsplit

import httpx


class AdresseRefusee(Exception):
    """Adresse invalide, ou qui mène à la box elle-même."""


class TelechargementEchoue(Exception):
    """Le serveur distant ne répond pas comme il faut."""


def ip_interdite(texte: str) -> bool:
    """Vrai pour la box elle-même (127.x, ::1, 0.0.0.0, ::), le lien local et le multicast."""
    try:
        ip = ipaddress.ip_address(str(texte).split("%")[0])
    except ValueError:
        return True
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_loopback or ip.is_unspecified or ip.is_link_local or ip.is_multicast


async def verifier_adresse(url: str) -> None:
    """AdresseRefusee si l'adresse n'est pas http(s) ou si elle mène à la box elle-même."""
    try:
        morceaux = urlsplit(url)
        port = morceaux.port or (443 if morceaux.scheme == "https" else 80)
    except ValueError:
        raise AdresseRefusee("Adresse invalide")
    if morceaux.scheme not in ("http", "https") or not morceaux.hostname:
        raise AdresseRefusee("Adresse web attendue (http:// ou https://)")
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(
            morceaux.hostname, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError):
        raise AdresseRefusee("Serveur introuvable")
    if not infos or any(ip_interdite(info[4][0]) for info in infos):
        raise AdresseRefusee("Adresse refusée : elle mène à la box elle-même")


def _verifier_adresse_jointe(reponse: httpx.Response) -> None:
    """Contre le piège « le nom change d'adresse entre la vérification et la connexion »."""
    flux = reponse.extensions.get("network_stream")
    if flux is None:
        return
    try:
        pair = flux.get_extra_info("server_addr")
    except Exception:
        pair = None
    if pair and ip_interdite(str(pair[0])):
        raise AdresseRefusee("Adresse refusée : elle mène à la box elle-même")


async def telecharger_texte(url: str, taille_max: int = 5 * 1024 * 1024,
                            delai: float = 15.0, redirections: int = 5) -> str:
    """Le texte d'une page web (RSS, OPML…), en refusant toute adresse de la box."""
    async with httpx.AsyncClient(timeout=delai, follow_redirects=False,
                                 headers={"User-Agent": "AudioBox/1.6"}) as client:
        for _ in range(redirections + 1):
            await verifier_adresse(url)
            async with client.stream("GET", url) as r:
                _verifier_adresse_jointe(r)
                if r.is_redirect:
                    cible = r.headers.get("location", "")
                    if not cible:
                        raise TelechargementEchoue("Redirection sans adresse")
                    url = urljoin(url, cible)
                    continue
                if r.status_code != 200:
                    raise TelechargementEchoue(f"Le serveur a répondu {r.status_code}")
                morceaux, taille = [], 0
                async for bout in r.aiter_bytes():
                    taille += len(bout)
                    if taille > taille_max:
                        raise TelechargementEchoue("Fichier trop gros")
                    morceaux.append(bout)
                return _decoder(b"".join(morceaux), r.charset_encoding)
        raise TelechargementEchoue("Trop de redirections")


def _decoder(brut: bytes, annonce: str | None) -> str:
    """Le bon jeu de caractères : celui du serveur, sinon celui écrit en tête du XML."""
    encodage = annonce
    if not encodage:
        m = re.match(rb'\s*<\?xml[^>]*encoding=["\']([A-Za-z0-9._-]+)["\']', brut[:300])
        encodage = m.group(1).decode() if m else "utf-8"
    if brut.startswith(b"\xef\xbb\xbf"):
        encodage = "utf-8-sig"
    try:
        return brut.decode(encodage, errors="replace")
    except LookupError:
        return brut.decode("utf-8", errors="replace")
