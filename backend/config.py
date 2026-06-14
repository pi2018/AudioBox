import json, os, logging
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken

CONFIG_PATH = Path("/opt/jv/config/config.json")
KEY_PATH    = Path("/opt/jv/config/.secret.key")
logger      = logging.getLogger("config")


def _get_fernet() -> Fernet:
    try:
        if not KEY_PATH.exists():
            key = Fernet.generate_key()
            KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
            KEY_PATH.write_bytes(key)
            KEY_PATH.chmod(0o600)
            logger.info("Clé de chiffrement générée")
        return Fernet(KEY_PATH.read_bytes())
    except Exception as e:
        logger.error(f"Erreur clé de chiffrement: {e}")
        raise


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        raw = CONFIG_PATH.read_bytes()
        if not raw:
            return {}
        # Essayer le déchiffrement Fernet
        try:
            return json.loads(_get_fernet().decrypt(raw))
        except (InvalidToken, Exception):
            # Fallback : fichier en clair (première utilisation / migration)
            try:
                data = json.loads(raw)
                # Rechiffrer immédiatement
                save_config(data)
                logger.info("Config migrée vers le format chiffré")
                return data
            except json.JSONDecodeError:
                logger.error("Config corrompue, réinitialisation")
                return {}
    except Exception as e:
        logger.error(f"Erreur lecture config: {e}")
        return {}


def save_config(data: dict) -> None:
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        encrypted = _get_fernet().encrypt(json.dumps(data, indent=2).encode())
        # Écriture atomique : fichier temporaire puis rename
        tmp = CONFIG_PATH.with_suffix(".tmp")
        tmp.write_bytes(encrypted)
        tmp.chmod(0o600)
        tmp.rename(CONFIG_PATH)
    except Exception as e:
        logger.error(f"Erreur sauvegarde config: {e}")
        raise


def update_config(updates: dict) -> dict:
    cfg = load_config()
    cfg.update(updates)
    save_config(cfg)
    return cfg
