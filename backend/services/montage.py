"""
Livres audio en plusieurs fichiers : un seul « montage » pour le lecteur.

Avant, seul le premier fichier d'un livre était joué. Maintenant tous les fichiers
sont mis bout à bout dans une liste de montage mpv (format EDL) :

    edl://%48%https://abs/api/items/X/file/1,0,1834.2;%48%https://abs/api/items/X/file/2,0,1790.0

Pour mpv c'est UN seul morceau : la position, la durée, l'avance rapide et les
chapitres d'Audiobookshelf (qui comptent depuis le début du livre) marchent donc
tels quels, sans rien recalculer. Aucune dépendance : essayé par tests/test_montage.py.
"""

PREFIXE = "edl://"


def fabriquer(segments: list[tuple[str, float]]) -> str:
    """[(adresse, durée en s), …] → une adresse pour mpv. Un seul fichier : l'adresse telle quelle."""
    if not segments:
        raise ValueError("Aucun fichier audio")
    if len(segments) == 1:
        return segments[0][0]
    morceaux = []
    for adresse, duree in segments:
        # %longueur% : l'adresse est prise telle quelle, même avec « , » ou « ; » dedans.
        entree = f"%{len(adresse)}%{adresse}"
        if duree and duree > 0:
            entree += f",0,{duree:.3f}"
        morceaux.append(entree)
    return PREFIXE + ";".join(morceaux)


def adresses(uri: str) -> list[str]:
    """Les adresses contenues dans un montage (ou l'adresse elle-même). ValueError si mal formé."""
    if not uri.startswith(PREFIXE):
        return [uri]
    texte = uri[len(PREFIXE):]
    sortie, i = [], 0
    while i < len(texte):
        if texte[i] == "%":
            fin = texte.index("%", i + 1)
            n = int(texte[i + 1:fin])
            debut = fin + 1
            adresse = texte[debut:debut + n]
            if len(adresse) != n:
                raise ValueError("Montage tronqué")
            sortie.append(adresse)
            i = debut + n
        else:
            fin = texte.find(",", i)
            fin2 = texte.find(";", i)
            bornes = [x for x in (fin, fin2) if x != -1]
            j = min(bornes) if bornes else len(texte)
            sortie.append(texte[i:j])
            i = j
        # Sauter les paramètres « ,début,durée » jusqu'au « ; » suivant.
        suite = texte.find(";", i)
        if suite == -1:
            break
        i = suite + 1
    if not sortie:
        raise ValueError("Montage vide")
    return sortie


def segments_abs(base: str, item_id: str, fichiers: list[dict]) -> list[tuple[str, float]]:
    """
    Les fichiers audio d'un livre Audiobookshelf, dans l'ordre, avec leur durée.
    Sans les fichiers qu'Audiobookshelf a écartés (« exclure » ou illisibles) : ils ne
    font pas partie du livre, et leur durée décalerait les chapitres.
    """
    gardes = [f for f in fichiers if not f.get("exclude") and not f.get("invalid")] or fichiers
    tries = sorted(gardes, key=lambda f: (f.get("index") if f.get("index") is not None else 10**9,
                                        str(f.get("metadata", {}).get("filename", ""))))
    sortie = []
    for f in tries:
        ino = f.get("ino", f.get("id", ""))
        if not ino:
            continue
        sortie.append((f"{base}/api/items/{item_id}/file/{ino}", float(f.get("duration") or 0)))
    return sortie
