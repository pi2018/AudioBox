from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import Response
import asyncio, subprocess, json, logging
from config import load_config, save_config
from routers.settings import verify_token

router = APIRouter(prefix="/system", tags=["system"])
logger = logging.getLogger("system")

FICHIER_VERSION = "/opt/jv/version.json"
ETAT_MAJ = "/opt/jv/logs/mise-a-jour.etat"      # écrit par system/update-audiobox.sh
JOURNAL_MAJ = "/opt/jv/logs/mise-a-jour.log"


def _lire_version() -> dict:
    try:
        with open(FICHIER_VERSION, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"version": "?"}


# La version du programme qui tourne VRAIMENT, lue au démarrage du serveur. Si le
# fichier dit autre chose, le serveur n'a pas été relancé après une mise à jour :
# c'est ce qui s'était passé en 1.5 (numéro neuf, ancien programme).
VERSION_EN_COURS = _lire_version().get("version", "?")


async def _executer(cmd: list, **options) -> subprocess.CompletedProcess:
    """Une commande système dans un fil à part : la box ne se fige plus pendant l'attente."""
    return await asyncio.to_thread(subprocess.run, cmd, **options)


def _plus_tard(secondes: float, cmd: list) -> None:
    asyncio.get_running_loop().call_later(secondes, lambda: subprocess.Popen(cmd))


# ── Redémarrage / Arrêt ───────────────────────────────────────────────────────

@router.post("/reboot")
async def reboot(_: bool = Depends(verify_token)):
    """Redémarre le Raspberry Pi."""
    logger.info("Reboot demandé depuis le dashboard")
    _plus_tard(2, ["sudo", "-n", "/usr/sbin/reboot"])
    return {"status": "rebooting", "message": "Redémarrage dans 2 secondes..."}


@router.post("/shutdown")
async def shutdown(_: bool = Depends(verify_token)):
    """Éteint le Raspberry Pi."""
    logger.info("Shutdown demandé depuis le dashboard")
    _plus_tard(2, ["sudo", "-n", "/usr/sbin/shutdown", "-h", "now"])
    return {"status": "shutting_down", "message": "Arrêt dans 2 secondes..."}


@router.post("/restart-backend")
async def restart_backend(_: bool = Depends(verify_token)):
    """Redémarre uniquement le backend AudioBox."""
    _plus_tard(1, ["sudo", "-n", "/usr/bin/systemctl", "restart", "jv-backend"])
    return {"status": "restarting", "message": "Backend redémarre..."}


# ── Mise à jour yt-dlp ────────────────────────────────────────────────────────

@router.get("/ytdlp-version")
async def ytdlp_version():
    """Retourne la version actuelle de yt-dlp."""
    try:
        r = await _executer(["yt-dlp", "--version"], capture_output=True, text=True, timeout=10)
        return {"version": r.stdout.strip(), "available": True}
    except Exception:
        return {"version": "non installé", "available": False}


@router.post("/update-ytdlp")
async def update_ytdlp(_: bool = Depends(verify_token)):
    """Met à jour yt-dlp vers la dernière version (script autorisé dans sudoers)."""
    try:
        r = await _executer(["sudo", "-n", "/opt/jv/system/update-ytdlp.sh"],
                            capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Timeout — vérifiez votre connexion")
    # Avant, l'échec passait inaperçu et l'écran affichait « mis à jour ».
    if r.returncode != 0:
        detail = (r.stderr or r.stdout).strip()[:200] or "échec"
        raise HTTPException(status_code=500, detail=f"Mise à jour impossible : {detail}")
    v = await _executer(["yt-dlp", "--version"], capture_output=True, text=True, timeout=10)
    return {"status": "updated", "version": v.stdout.strip()}


@router.post("/update-audiobox")
async def update_audiobox(_: bool = Depends(verify_token)):
    """Télécharge la dernière AudioBox sur GitHub et la réinstalle (en arrière-plan)."""
    try:
        r = await _executer(["sudo", "-n", "/opt/jv/system/update-audiobox.sh"],
                            capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Le lancement de la mise à jour ne répond pas")
    sortie = (r.stdout + "\n" + r.stderr).strip()
    if r.returncode == 2:
        raise HTTPException(status_code=409, detail="Une mise à jour est déjà en cours")
    if r.returncode != 0:
        raise HTTPException(status_code=500, detail=sortie[:200] or "échec")
    return {"status": "started",
            "message": "Mise à jour lancée : la box redémarre toute seule dans quelques minutes."}


def _etat_maj() -> str:
    """« en_cours », « ok 1.6.0 » ou « echec : … » (vide si jamais mise à jour depuis l'écran)."""
    try:
        with open(ETAT_MAJ, encoding="utf-8", errors="replace") as f:
            return f.read().strip()[:300]
    except OSError:
        return ""


@router.get("/version")
async def version():
    v = _lire_version()
    v["en_cours"] = VERSION_EN_COURS
    v["maj"] = _etat_maj()
    return v


# ── Backup / Restore ──────────────────────────────────────────────────────────

@router.get("/backup")
async def backup_config(_: bool = Depends(verify_token)):
    """Télécharge la configuration en clair (JSON)."""
    cfg = load_config()
    # La sauvegarde contient la clé Audiobookshelf : elle est donc réservée au token.
    safe = json.dumps(cfg, indent=2, ensure_ascii=False)
    return Response(
        content=safe,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=audiobox-backup.json"}
    )


@router.post("/restore")
async def restore_config(data: dict, _: bool = Depends(verify_token)):
    """Restaure la configuration depuis un backup JSON."""
    try:
        save_config(data)
        return {"status": "restored", "keys": list(data.keys())}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Logs ──────────────────────────────────────────────────────────────────────

@router.get("/logs")
async def get_logs(lines: int = 100, source: str = "serveur", _: bool = Depends(verify_token)):
    """Les derniers messages du serveur, ou (source=maj) le journal de la dernière mise à jour."""
    lines = max(1, min(lines, 500))
    if source == "maj":
        try:
            with open(JOURNAL_MAJ, encoding="utf-8", errors="replace") as f:
                texte = "".join(f.readlines()[-lines:])
        except OSError:
            texte = "Aucune mise à jour lancée depuis l'écran pour l'instant."
        return {"logs": texte, "lines": texte.count("\n")}
    try:
        r = await _executer(
            ["journalctl", "-u", "jv-backend", "-n", str(lines), "--no-pager", "--output=short"],
            capture_output=True, text=True, timeout=10
        )
        texte = r.stdout or r.stderr
        return {"logs": texte, "lines": texte.count('\n')}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _mesures() -> dict:
    def run(cmd):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            return r.stdout.strip()
        except Exception:
            return "—"

    disk = run(["df", "-h", "/"])
    mem = run(["free", "-h"])
    return {
        "temperature": run(["vcgencmd", "measure_temp"]),
        "uptime":      run(["uptime", "-p"]),
        "disk":        disk.split('\n')[-1] if disk else "—",
        "memory":      mem.split('\n')[1] if mem.count('\n') >= 1 else "—",
        "ytdlp":       run(["yt-dlp", "--version"]),
        "services": {
            "backend":   run(["systemctl", "is-active", "jv-backend"]),
        }
    }


@router.get("/status")
async def system_status():
    """Retourne l'état général du système."""
    return await asyncio.to_thread(_mesures)
