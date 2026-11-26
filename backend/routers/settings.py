from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, HttpUrl, field_validator
import asyncio, subprocess, secrets, os, re, logging
from config import load_config, update_config

router   = APIRouter(prefix="/settings", tags=["settings"])
security = HTTPBearer(auto_error=False)
logger   = logging.getLogger("settings")

# v1.4 : nouveau fichier, donc NOUVEAU token. L'ancien a pu être lu sur le réseau
# (il était écrit dans le journal, lisible sans code). L'ancien fichier est effacé.
TOKEN_FILE = "/opt/jv/config/.dashboard_token_v2"
_ANCIEN_TOKEN = "/opt/jv/config/.dashboard_token"

# Racines où l'on a le droit de monter un partage NAS.
RACINES_NAS = ("/opt/jv/nas", "/mnt")


def _get_token() -> str:
    try:
        if os.path.exists(_ANCIEN_TOKEN):
            os.remove(_ANCIEN_TOKEN)
        if os.path.exists(TOKEN_FILE):
            token = open(TOKEN_FILE).read().strip()
            if token:
                return token
        token = secrets.token_urlsafe(32)
        os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
        # Créé directement en 600 : jamais lisible par les autres, même un instant.
        fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(token)
        logger.info("Nouveau token du tableau de bord créé")
        return token
    except Exception as e:
        logger.error(f"Erreur génération token: {e}")
        raise HTTPException(status_code=500, detail="Impossible de générer le token")


def _vient_de_la_box(request: Request) -> bool:
    """L'écran tactile tourne sur la box elle-même : il n'a pas à taper le token."""
    hote = request.client.host if request.client else ""
    return hote in ("127.0.0.1", "::1")


def verify_token(request: Request,
                 creds: HTTPAuthorizationCredentials | None = Depends(security)):
    if _vient_de_la_box(request):
        return True
    if creds is None or not secrets.compare_digest(creds.credentials, _get_token()):
        raise HTTPException(status_code=401, detail="Token invalide")
    return True


def _config_sans_secrets(cfg: dict) -> dict:
    """La configuration renvoyée à l'écran : jamais de mot de passe ni de clé."""
    safe = {k: v for k, v in cfg.items()
            if not any(s in k.lower() for s in ["password", "secret", "key", "token"])}
    if cfg.get("abs_api_key"):
        safe["abs_api_key"] = "••••••••" + cfg["abs_api_key"][-4:]
    return safe


def chemin_nas_autorise(chemin: str) -> str | None:
    """Le chemin réel (sans « .. » ni lien), s'il est bien sous une racine NAS ; sinon None."""
    reel = os.path.realpath(chemin)
    for racine in RACINES_NAS:
        if reel.startswith(racine + os.sep):
            return reel
    return None


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


_CONTROLE = re.compile(r"[\x00-\x1f\x7f]")


class NASMount(BaseModel):
    host: str
    share: str
    mount_point: str
    username: str = ""
    password: str = ""

    @field_validator("mount_point")
    @classmethod
    def validate_mount_point(cls, v):
        if _CONTROLE.search(v or ""):
            raise ValueError("Point de montage invalide")
        # realpath : « /mnt/../etc » devenait sinon un montage sur /etc, en root.
        reel = chemin_nas_autorise(v)
        if not reel:
            raise ValueError("Point de montage doit être dans /opt/jv/nas/ ou /mnt/")
        return reel

    @field_validator("host")
    @classmethod
    def validate_host(cls, v):
        v = (v or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9.\-]+", v):
            raise ValueError("Adresse du NAS invalide (lettres, chiffres, points, tirets)")
        return v

    @field_validator("share")
    @classmethod
    def validate_share(cls, v):
        v = (v or "").strip().strip("/")
        # Une virgule ou un retour à la ligne permettrait d'ajouter des options de montage.
        if not v or "," in v or _CONTROLE.search(v):
            raise ValueError("Nom du partage invalide")
        return v

    @field_validator("username")
    @classmethod
    def validate_username(cls, v):
        if re.search(r"[,=]", v or "") or _CONTROLE.search(v or ""):
            raise ValueError("Nom d'utilisateur invalide")
        return (v or "").strip()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        # Il passe sur une ligne : un retour à la ligne le couperait.
        if re.search(r"[\n\r\x00]", v or ""):
            raise ValueError("Mot de passe invalide")
        return v or ""


class RadioStation(BaseModel):
    name: str
    url: str
    favicon: str = ""   # logo (avant : perdu à l'enregistrement)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        v = (v or "").strip()
        if not v:
            raise ValueError("Nom de la radio vide")
        return v[:200]

    @field_validator("url")
    @classmethod
    def validate_url(cls, v):
        v = (v or "").strip()
        if not v.startswith("http://") and not v.startswith("https://"):
            raise ValueError("L'URL doit commencer par http:// ou https://")
        return v

    @field_validator("favicon")
    @classmethod
    def validate_favicon(cls, v):
        v = (v or "").strip()
        return v if v.startswith(("http://", "https://")) else ""


class AudioOutput(BaseModel):
    output: str

class Webhook(BaseModel):
    url: str
    events: list = ["play", "pause", "stop", "finished"]
    name: str = ""


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/")
async def get_settings(_: bool = Depends(verify_token)):
    return _config_sans_secrets(load_config())


@router.post("/abs")
async def set_abs(data: ABSSettings, _: bool = Depends(verify_token)):
    return _config_sans_secrets(update_config({"abs_url": str(data.url), "abs_api_key": data.api_key}))


@router.post("/nas/mount")
async def mount_nas(data: NASMount, _: bool = Depends(verify_token)):
    script = "/opt/jv/system/mount-nas.sh"
    if not os.path.exists(script):
        raise HTTPException(status_code=503, detail=f"Script de montage introuvable: {script}")

    try:
        # Le mot de passe passe par l'entrée standard, jamais sur la ligne de commande
        # (qui est visible par tous les programmes de la box avec « ps »).
        # Dans un fil à part : avant, toute la box (écran, lecture) se figeait pendant
        # le montage, jusqu'à 20 secondes.
        result = await asyncio.to_thread(
            subprocess.run,
            ["sudo", "-n", script, data.host, data.share, data.mount_point, data.username],
            input=data.password + "\n", capture_output=True, text=True, timeout=30
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Timeout lors du montage NAS")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if result.returncode != 0:
        err = (result.stderr.strip() or result.stdout.strip()).replace(data.password, "•••") if data.password else (result.stderr.strip() or result.stdout.strip())
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
    reel = chemin_nas_autorise(mount_point)
    if not reel:
        raise HTTPException(status_code=400, detail="Point de montage non autorisé")
    mount_point = reel
    script = "/opt/jv/system/umount-nas.sh"
    if not os.path.exists(script):
        raise HTTPException(status_code=503, detail="Script de démontage introuvable")

    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ["sudo", "-n", script, mount_point],
            capture_output=True, text=True, timeout=15
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Timeout lors du démontage")

    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=(result.stderr or result.stdout).strip() or "échec")

    # Retirer de la config
    mounts = [m for m in load_config().get("nas_mounts", [])
              if m.get("mount_point") != mount_point]
    update_config({"nas_mounts": mounts})
    return {"status": "unmounted", "mount_point": mount_point}


@router.post("/radios")
async def save_radios(stations: list[RadioStation], _: bool = Depends(verify_token)):
    return _config_sans_secrets(update_config({"radios": [s.model_dump() for s in stations]}))


@router.get("/radios")
async def get_radios():
    return load_config().get("radios", [])


@router.post("/output")
async def set_output(data: AudioOutput, _: bool = Depends(verify_token)):
    if data.output not in ("jack", "auto", "hdmi"):
        raise HTTPException(status_code=400, detail="Sortie audio inconnue")
    return _config_sans_secrets(update_config({"default_output": data.output}))


@router.get("/webhooks")
async def get_webhooks(_: bool = Depends(verify_token)):
    return load_config().get("webhooks", [])


@router.post("/webhooks")
async def save_webhooks(webhooks: list[Webhook], _: bool = Depends(verify_token)):
    return _config_sans_secrets(update_config({"webhooks": [w.model_dump() for w in webhooks]}))


@router.get("/setup-info")
async def setup_info(request: Request):
    """
    Le token, mais seulement pour l'écran de la box elle-même : il le montre pour
    qu'on le recopie sur le téléphone. Depuis le réseau, on ne le donne jamais.
    """
    if _vient_de_la_box(request):
        return {"configured": False, "token": _get_token()}
    return {"configured": True}


@router.get("/token-hint")
async def token_hint():
    return {"message": "Le token est sur la box, dans ~/audiobox-token.txt (écran : page Paramètres)."}
