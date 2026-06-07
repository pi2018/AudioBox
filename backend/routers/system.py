from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import subprocess, secrets, os, json, asyncio, logging
from config import load_config, save_config
from routers.settings import verify_token

router = APIRouter(prefix="/system", tags=["system"])
logger = logging.getLogger("system")


# ── Redémarrage / Arrêt ───────────────────────────────────────────────────────

@router.post("/reboot")
async def reboot(_: bool = Depends(verify_token)):
    """Redémarre le Raspberry Pi."""
    logger.info("Reboot demandé depuis le dashboard")
    asyncio.get_event_loop().call_later(2, lambda: subprocess.run(["sudo", "reboot"]))
    return {"status": "rebooting", "message": "Redémarrage dans 2 secondes..."}


@router.post("/shutdown")
async def shutdown(_: bool = Depends(verify_token)):
    """Éteint le Raspberry Pi."""
    logger.info("Shutdown demandé depuis le dashboard")
    asyncio.get_event_loop().call_later(2, lambda: subprocess.run(["sudo", "shutdown", "-h", "now"]))
    return {"status": "shutting_down", "message": "Arrêt dans 2 secondes..."}


@router.post("/restart-backend")
async def restart_backend(_: bool = Depends(verify_token)):
    """Redémarre uniquement le backend AudioBox."""
    asyncio.get_event_loop().call_later(1, lambda: subprocess.run(
        ["sudo", "systemctl", "restart", "jv-backend"]
    ))
    return {"status": "restarting", "message": "Backend redémarre..."}


# ── Mise à jour yt-dlp ────────────────────────────────────────────────────────

@router.get("/ytdlp-version")
async def ytdlp_version():
    """Retourne la version actuelle de yt-dlp."""
    try:
        r = subprocess.run(["yt-dlp", "--version"],
                           capture_output=True, text=True, timeout=10)
        return {"version": r.stdout.strip(), "available": True}
    except Exception:
        return {"version": "non installé", "available": False}


@router.post("/update-ytdlp")
async def update_ytdlp(_: bool = Depends(verify_token)):
    """Met à jour yt-dlp vers la dernière version."""
    try:
        r = subprocess.run(
            ["sudo", "curl", "-sSL",
             "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp",
             "-o", "/usr/local/bin/yt-dlp"],
            capture_output=True, text=True, timeout=30
        )
        subprocess.run(["sudo", "chmod", "+x", "/usr/local/bin/yt-dlp"],
                       capture_output=True, timeout=5)
        # Vérifier la nouvelle version
        r2 = subprocess.run(["yt-dlp", "--version"],
                             capture_output=True, text=True, timeout=10)
        return {"status": "updated", "version": r2.stdout.strip()}
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Timeout — vérifiez votre connexion")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Backup / Restore ──────────────────────────────────────────────────────────

@router.get("/backup")
async def backup_config(_: bool = Depends(verify_token)):
    """Télécharge la configuration en clair (JSON)."""
    cfg = load_config()
    # Masquer les mots de passe NAS mais garder tout le reste
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
async def get_logs(lines: int = 100):
    """Retourne les derniers logs du backend."""
    try:
        r = subprocess.run(
            ["journalctl", "-u", "jv-backend", "-n", str(min(lines, 500)),
             "--no-pager", "--output=short"],
            capture_output=True, text=True, timeout=10
        )
        return {"logs": r.stdout, "lines": r.stdout.count('\n')}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def system_status():
    """Retourne l'état général du système."""
    def run(cmd):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            return r.stdout.strip()
        except Exception:
            return "—"

    temp = run(["vcgencmd", "measure_temp"])
    uptime = run(["uptime", "-p"])
    disk = run(["df", "-h", "/"])
    mem = run(["free", "-h"])

    # Version yt-dlp
    ytdlp = run(["yt-dlp", "--version"])

    # État des services
    backend = run(["systemctl", "is-active", "jv-backend"])
    bluetooth = run(["systemctl", "is-active", "bluetooth"])

    return {
        "temperature": temp,
        "uptime":      uptime,
        "disk":        disk.split('\n')[-1] if disk else "—",
        "memory":      mem.split('\n')[1] if mem else "—",
        "ytdlp":       ytdlp,
        "services": {
            "backend":   backend,
            "bluetooth": bluetooth,
        }
    }
