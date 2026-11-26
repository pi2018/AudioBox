"""
Essais : la box ne télécharge jamais une adresse qui mène à elle-même (sinon le code
admin et la clé Audiobookshelf fuyaient vers le réseau). python3 -m pytest backend/tests
"""
import asyncio
import os
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services import reseau  # noqa: E402


@pytest.mark.parametrize("ip", ["127.0.0.1", "127.1.2.3", "::1", "0.0.0.0", "::",
                                "::ffff:127.0.0.1", "169.254.1.1", "fe80::1", "224.0.0.1",
                                "pas-une-ip"])
def test_adresses_de_la_box_refusees(ip):
    assert reseau.ip_interdite(ip)


@pytest.mark.parametrize("ip", ["192.168.178.113", "10.0.0.5", "93.184.216.34", "2a00:1450::1"])
def test_appareils_de_la_maison_et_internet_permis(ip):
    assert not reseau.ip_interdite(ip)


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8000/api/settings/setup-info",
    "http://localhost:8000/api/system/backup",
    "http://[::1]:8000/",
    "http://0.0.0.0:8000/",
    "http://2130706433:8000/",          # 127.0.0.1 écrit en nombre
    "file:///etc/passwd",
    "ftp://exemple/x",
    "http://",
    "http://127.0.0.1:99999/",
])
def test_verification_refuse(url):
    with pytest.raises(reseau.AdresseRefusee):
        asyncio.run(reseau.verifier_adresse(url))


def test_verification_accepte_le_reseau_local():
    asyncio.run(reseau.verifier_adresse("http://192.168.178.113:13378/feed.xml"))


def test_jeu_de_caracteres():
    latin = '<?xml version="1.0" encoding="ISO-8859-1"?><t>été</t>'.encode("latin-1")
    assert reseau._decoder(latin, None).endswith("<t>été</t>")
    assert reseau._decoder(b"\xef\xbb\xbf<rss/>", None) == "<rss/>"
    assert reseau._decoder("été".encode(), "utf-8") == "été"
    assert reseau._decoder("été".encode(), "inconnu-123") == "été"


def _ip_non_locale() -> str | None:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.123", 9))     # aucun paquet n'est envoyé
        ip = s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()
    return None if reseau.ip_interdite(ip) else ip


@pytest.fixture
def serveur():
    """Un petit serveur web « de la maison » : un flux, et une redirection vers la box."""
    ip = _ip_non_locale()
    if not ip:
        pytest.skip("pas d'adresse réseau autre que la boucle locale")

    class Pages(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/flux.xml":
                corps = b"<rss><channel><title>Essai</title></channel></rss>"
                self.send_response(200)
                self.send_header("Content-Type", "application/rss+xml")
                self.send_header("Content-Length", str(len(corps)))
                self.end_headers()
                self.wfile.write(corps)
            elif self.path == "/vers-la-box":
                self.send_response(302)
                self.send_header("Location", "http://127.0.0.1:8000/api/settings/setup-info")
                self.end_headers()
            elif self.path == "/vers-le-flux":
                self.send_response(301)
                self.send_header("Location", "/flux.xml")
                self.end_headers()
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("0.0.0.0", 0), Pages)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://{ip}:{httpd.server_address[1]}"
    httpd.shutdown()


def test_telechargement_normal_et_redirection_permise(serveur):
    assert "<title>Essai</title>" in asyncio.run(reseau.telecharger_texte(serveur + "/flux.xml"))
    assert "<title>Essai</title>" in asyncio.run(reseau.telecharger_texte(serveur + "/vers-le-flux"))


def test_redirection_vers_la_box_refusee(serveur):
    with pytest.raises(reseau.AdresseRefusee):
        asyncio.run(reseau.telecharger_texte(serveur + "/vers-la-box"))


def test_erreur_du_serveur(serveur):
    with pytest.raises(reseau.TelechargementEchoue):
        asyncio.run(reseau.telecharger_texte(serveur + "/absent"))
