from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, HttpUrl, field_validator
import subprocess, secrets, os, logging
from config import load_config, update_config

router   = APIRouter(prefix="/settings", tags=["settings"])
security = HTTPBearer()
logger   = logging.getLogger("settings")

_TOKEN_FILE = "/opt/jv/config/.dashboard_token"


def _get_token() -> str:
    try:
        if os.path.exists(_TOKEN_FILE):
            token = open(_TOKEN_FILE).read().strip()
            if token:
                return token
        token = secrets.token_urlsafe(32)
        os.makedirs(os.path.dirname(_TOKEN_FILE), exist_ok=True)
        with open(_TOKEN_FILE, "w") as f:
            f.write(token)
        os.chmod(_TOKEN_FILE, 0o600)
        logger.info(f"=== AudioBox Dashboard Token: {token} ===")
        return token
    except Exception as e:
        logger.error(f"Erreur génération token: {e}")
        raise HTTPException(status_code=500, detail="Impossible de générer le token")


def verify_token(creds: HTTPAuthorizationCredentials = Depends(security)):
    if not secrets.compare_digest(creds.credentials, _get_token()):
        raise HTTPException(status_code=401, detail="Token invalide")
    return True


# ── Schémas Pydantic ──────────────────────────────────────────────────────────

class ABSSettings(BaseModel):
    url: HttpUrl
    api_key: str

    @field_validator("api_key")
    @classmethod
    def api_key_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("La clé API ne peut pas être vide")
        return v.strip()


class NASMount(BaseModel):
    host: str
    share: str
    mount_point: str
    username: str = ""
    password: str = ""

    @field_validator("mount_point")
    @classmethod
    def validate_mount_point(cls, v):
        if not v.startswith("/opt/jv/nas") and not v.startswith("/mnt"):
            raise ValueError("Point de montage doit être sous /opt/jv/nas/ ou /mnt/")
        return v

    @field_validator("host")
    @classmethod
    def validate_host(cls, v):
        if not v or not v.strip():
            raise ValueError("L'adresse du NAS ne peut pas être vide")
        return v.strip()


class RadioStation(BaseModel):
    name: str
    url: str

    @field_validator("url")
    @classmethod
    def validate_url(cls, v):
        if not v.startswith("http://") and not v.startswith("https://"):
            raise ValueError("L'URL doit commencer par http:// ou https://")
        return v


class AudioOutput(BaseModel):
    output: str

class Webhook(BaseModel):
    url: str
    events: list = ["play", "pause", "stop", "finished"]
    name: str = ""


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/")
async def get_settings(_: bool = Depends(verify_token)):
    cfg = load_config()
    # Masquer tous les champs sensibles
    safe = {k: v for k, v in cfg.items()
            if not any(s in k.lower() for s in ["password", "secret", "key", "token"])}
    # Masquer partiellement la clé API ABS
    if "abs_api_key" in cfg and cfg["abs_api_key"]:
        safe["abs_api_key"] = "••••••••" + cfg["abs_api_key"][-4:]
    return safe


@router.post("/abs")
async def set_abs(data: ABSSettings, _: bool = Depends(verify_token)):
    return update_config({"abs_url": str(data.url), "abs_api_key": data.api_key})


@router.post("/nas/mount")
async def mount_nas(data: NASMount, _: bool = Depends(verify_token)):
    script = "/opt/jv/system/mount-nas.sh"
    if not os.path.exists(script):
        raise HTTPException(status_code=503, detail=f"Script de montage introuvable: {script}")

    try:
        result = subprocess.run(
            ["sudo", script, data.host, data.share, data.mount_point,
             data.username, data.password],
            capture_output=True, text=True, timeout=20
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Timeout lors du montage NAS")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if result.returncode != 0:
        err = result.stderr.strip() or result.stdout.strip()
        raise HTTPException(status_code=500, detail=f"Montage échoué: {err}")

    # Sauvegarder sans le mot de passe
    mounts = load_config().get("nas_mounts", [])
    safe_mount = {k: v for k, v in data.model_dump().items() if k != "password"}
    # Remplacer si même mount_point, sinon ajouter
    mounts = [m for m in mounts if m.get("mount_point") != data.mount_point]
    mounts.append(safe_mount)
    update_config({"nas_mounts": mounts})
    return {"status": "mounted", "mount_point": data.mount_point}


@router.post("/nas/umount")
async def umount_nas(mount_point: str, _: bool = Depends(verify_token)):
    script = "/opt/jv/system/umount-nas.sh"
    if not os.path.exists(script):
        raise HTTPException(status_code=503, detail="Script de démontage introuvable")

    try:
        result = subprocess.run(
            ["sudo", script, mount_point],
            capture_output=True, text=True, timeout=10
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Timeout lors du démontage")

    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=result.stderr.strip())

    # Retirer de la config
    mounts = [m for m in load_config().get("nas_mounts", [])
              if m.get("mount_point") != mount_point]
    update_config({"nas_mounts": mounts})
    return {"status": "unmounted", "mount_point": mount_point}


@router.post("/radios")
async def save_radios(stations: list[RadioStation], _: bool = Depends(verify_token)):
    return update_config({"radios": [s.model_dump() for s in stations]})


@router.get("/radios")
async def get_radios():
    return load_config().get("radios", [])


@router.post("/output")
async def set_output(data: AudioOutput, _: bool = Depends(verify_token)):
    return update_config({"default_output": data.output})


@router.get("/webhooks")
async def get_webhooks(_: bool = Depends(verify_token)):
    return load_config().get("webhooks", [])


@router.post("/webhooks")
async def save_webhooks(webhooks: list[Webhook], _: bool = Depends(verify_token)):
    return update_config({"webhooks": [w.model_dump() for w in webhooks]})


@router.get("/token-hint")
async def token_hint():
    return {"message": "Consultez: journalctl -u jv-backend | grep 'Token'"}
