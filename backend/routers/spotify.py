from fastapi import APIRouter
import subprocess, shutil

router = APIRouter(prefix="/spotify", tags=["spotify"])


def _librespot_available() -> bool:
    return shutil.which("librespot") is not None or \
           subprocess.run(["systemctl", "is-enabled", "audiobox-spotify"],
                          capture_output=True).returncode == 0


@router.get("/status")
async def status():
    result = subprocess.run(
        ["systemctl", "is-active", "audiobox-spotify"],
        capture_output=True, text=True
    )
    return {"running": result.stdout.strip() == "active",
            "available": _librespot_available()}


@router.post("/start")
async def start():
    subprocess.run(["systemctl", "start", "audiobox-spotify"],
                   capture_output=True)
    return {"status": "started"}


@router.post("/stop")
async def stop():
    subprocess.run(["systemctl", "stop", "audiobox-spotify"],
                   capture_output=True)
    return {"status": "stopped"}
