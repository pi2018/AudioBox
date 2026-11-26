"""Essais du montage des livres en plusieurs fichiers : python3 -m pytest backend/tests"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services import montage


def test_un_seul_fichier_reste_une_adresse_simple():
    assert montage.fabriquer([("https://abs/a.mp3", 10.0)]) == "https://abs/a.mp3"


def test_plusieurs_fichiers_donnent_un_montage_relu_a_l_identique():
    segs = [("https://abs/api/items/X/file/1", 1834.2), ("https://abs/api/items/X/file/2", 1790.0)]
    uri = montage.fabriquer(segs)
    assert uri.startswith("edl://")
    assert montage.adresses(uri) == [s[0] for s in segs]


def test_une_adresse_avec_virgule_et_point_virgule_reste_entiere():
    bizarre = "https://abs/f?a=1,2;3"
    uri = montage.fabriquer([(bizarre, 5), ("https://abs/b", 6)])
    assert montage.adresses(uri) == [bizarre, "https://abs/b"]


def test_ordre_des_fichiers_suit_l_index_abs():
    fichiers = [{"ino": "b", "index": 2, "duration": 20}, {"ino": "a", "index": 1, "duration": 10}]
    segs = montage.segments_abs("https://abs", "X", fichiers)
    assert [s[0] for s in segs] == ["https://abs/api/items/X/file/a", "https://abs/api/items/X/file/b"]
    assert segs[0][1] == 10.0


def test_montage_mal_forme_est_refuse():
    try:
        montage.adresses("edl://%999%https://abs/a")
    except ValueError:
        return
    assert False, "un montage tronqué aurait dû être refusé"


def test_une_adresse_hors_montage_est_rendue_telle_quelle():
    assert montage.adresses("https://radio/flux") == ["https://radio/flux"]
