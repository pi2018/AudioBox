#!/usr/bin/env python3
"""
Envoie la nouvelle APK de l'appli AudioBox sur le PocketBase de l'Unraid (collection
« audiobox_versions ») et l'ajoute au catalogue du store « Mes Apps ».
Lancé par GitHub Actions après la compilation (dossier android/).
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

BASE = os.environ.get("PB_URL", "").strip().rstrip("/")
EMAIL = os.environ.get("PB_EMAIL", "").strip()
PASSWORD = os.environ.get("PB_PASSWORD", "")
APK = os.environ.get("APK", "")
CODE = int(os.environ.get("VERSION_CODE", "0") or 0)
COLLECTION = "audiobox_versions"
A_GARDER = 5
LECTURE = "@request.auth.id != \"\""

# Fiche de l'appli dans le store. Si elle existe déjà, elle n'est pas modifiée (tu peux l'éditer dans PocketBase).
FICHE_STORE = {
    "nom": "AudioBox", "paquet": "com.jv.audiobox", "collection": COLLECTION, "ordre": 6,
    "description": "Télécommande de la box audio : lecture, radios, volume, minuterie de sommeil.",
}

CHAMPS_VERSIONS = [
    {"name": "versionCode", "type": "number", "required": True},
    {"name": "versionName", "type": "text", "max": 50},
    {"name": "notes", "type": "text", "max": 5000},
    {"name": "apk", "type": "file", "maxSelect": 1, "maxSize": 209715200, "mimeTypes": [], "thumbs": []},
    {"name": "created", "type": "autodate", "onCreate": True, "onUpdate": False},
    {"name": "updated", "type": "autodate", "onCreate": True, "onUpdate": True},
]

CHAMPS_CATALOGUE = [
    {"name": "nom", "type": "text", "required": True, "max": 100},
    {"name": "paquet", "type": "text", "required": True, "max": 200},
    {"name": "description", "type": "text", "max": 500},
    {"name": "collection", "type": "text", "required": True, "max": 64},
    {"name": "ordre", "type": "number"},
    {"name": "created", "type": "autodate", "onCreate": True, "onUpdate": False},
    {"name": "updated", "type": "autodate", "onCreate": True, "onUpdate": True},
]


def nom_version():
    """« 1.0.$buildNumber » dans app/build.gradle.kts -> « 1.0.42 »."""
    try:
        with open("app/build.gradle.kts", encoding="utf-8") as f:
            m = re.search(r'versionName\s*=\s*"([^"$]*)\$buildNumber"', f.read())
        if m:
            return m.group(1) + str(CODE)
    except OSError:
        pass
    return str(CODE)


def nouveautes():
    try:
        with open("NOUVEAUTES.txt", encoding="utf-8") as f:
            return f.read().strip()[:4000]
    except OSError:
        return ""


def requete(methode, chemin, donnees=None, jeton=None, entetes=None, delai=120):
    h = dict(entetes or {})
    if jeton:
        h["Authorization"] = jeton
    corps = donnees
    if isinstance(donnees, (dict, list)):
        corps = json.dumps(donnees).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + chemin, data=corps, method=methode, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=delai) as r:
            return r.status, json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        texte = e.read().decode(errors="replace")
        try:
            return e.code, json.loads(texte)
        except Exception:
            return e.code, {"message": texte[:300]}
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        # Serveur injoignable : un message clair au lieu d'une trace Python.
        return 0, {"message": f"serveur injoignable ({e})"}


def assurer_collection(jeton, nom, champs, regles=None, index=None):
    """Crée la collection si elle n'existe pas (par défaut : lecture pour les comptes connectés, écriture super-utilisateur)."""
    st, col = requete("GET", f"/api/collections/{nom}", jeton=jeton)
    if st == 200:
        return True
    if st != 404:
        print(f"::error::Lecture de la collection {nom} impossible ({st}) : {col}")
        return False
    corps = {"name": nom, "type": "base", "fields": champs,
             "listRule": LECTURE, "viewRule": LECTURE,
             "createRule": None, "updateRule": None, "deleteRule": None}
    if regles:
        corps.update(regles)
    if index:
        corps["indexes"] = index
    st, res = requete("POST", "/api/collections", corps, jeton=jeton)
    if st not in (200, 201):
        print(f"::error::Création de la collection {nom} impossible ({st}) : {res}")
        return False
    print(f"Collection {nom} créée sur le serveur.")
    return True


def ajouter_au_store(jeton):
    if not assurer_collection(jeton, "store_apps", CHAMPS_CATALOGUE):
        return
    filtre = urllib.parse.quote(f"paquet='{FICHE_STORE['paquet']}'")
    st, res = requete("GET", f"/api/collections/store_apps/records?filter={filtre}&perPage=1", jeton=jeton)
    if st == 200 and res.get("items"):
        return
    st, res = requete("POST", "/api/collections/store_apps/records", FICHE_STORE, jeton=jeton)
    if st in (200, 201):
        print("Catalogue : AudioBox ajoutée au store.")
    else:
        print(f"::warning::Catalogue : AudioBox non ajoutée ({st}) : {res}")


def main():
    if not BASE or not EMAIL or not PASSWORD:
        print("::warning::Secrets PB_URL / PB_EMAIL / PB_PASSWORD absents : APK non envoyée sur le serveur.")
        return 0
    if not APK or not os.path.isfile(APK):
        print(f"::error::APK introuvable : {APK}")
        return 1

    st, res = requete("POST", "/api/collections/_superusers/auth-with-password",
                      {"identity": EMAIL, "password": PASSWORD})
    if st != 200:
        print(f"::error::Connexion à PocketBase refusée ({st}) : {res.get('message')}")
        return 1
    jeton = res["token"]

    if not assurer_collection(jeton, COLLECTION, CHAMPS_VERSIONS):
        return 1
    ajouter_au_store(jeton)

    nom = nom_version()
    frontiere = uuid.uuid4().hex
    morceaux = []

    def champ(n, v):
        morceaux.append(f"--{frontiere}\r\nContent-Disposition: form-data; name=\"{n}\"\r\n\r\n{v}\r\n".encode())

    champ("versionCode", str(CODE))
    champ("versionName", nom)
    champ("notes", nouveautes())
    with open(APK, "rb") as f:
        octets = f.read()
    morceaux.append(
        (f"--{frontiere}\r\nContent-Disposition: form-data; name=\"apk\"; filename=\"audiobox-{CODE}.apk\"\r\n"
         f"Content-Type: application/vnd.android.package-archive\r\n\r\n").encode() + octets + b"\r\n")
    morceaux.append(f"--{frontiere}--\r\n".encode())
    st, res = requete("POST", f"/api/collections/{COLLECTION}/records", b"".join(morceaux), jeton=jeton,
                      entetes={"Content-Type": f"multipart/form-data; boundary={frontiere}"}, delai=600)
    if st not in (200, 201):
        print(f"::error::Envoi de l'APK refusé ({st}) : {res}")
        if st == 413:
            print("::error::Fichier trop gros pour le proxy : ajoute « client_max_body_size 200m; » "
                  "dans l'onglet Advanced de Nginx Proxy Manager.")
        return 1
    print(f"AudioBox {nom} (n° {CODE}) envoyée sur le serveur : {len(octets) // 1024} Ko.")

    st, liste = requete("GET", f"/api/collections/{COLLECTION}/records?sort=-versionCode&perPage=50", jeton=jeton)
    if st == 200:
        for ancienne in liste.get("items", [])[A_GARDER:]:
            requete("DELETE", f"/api/collections/{COLLECTION}/records/{ancienne['id']}", jeton=jeton)
    return 0


if __name__ == "__main__":
    sys.exit(main())
