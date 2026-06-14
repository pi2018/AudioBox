from fastapi import APIRouter, HTTPException
from pathlib import Path
import os
from config import load_config

router = APIRouter(prefix="/nas", tags=["nas"])

ALLOWED_ROOTS = ["/opt/audiobox/nas", "/mnt"]


def _is_safe_path(path: str) -> bool:
    """Vérifie que le chemin est dans une racine autorisée."""
    p = str(Path(path).resolve())
    return any(p.startswith(root) for root in ALLOWED_ROOTS)


@router.get("/mounts")
async def list_mounts():
    """Liste les points de montage NAS configurés et leur état."""
    mounts = load_config().get("nas_mounts", [])
    result = []
    for m in mounts:
        mp = m.get("mount_point", "")
        try:
            mounted = os.path.ismount(mp) if mp else False
        except Exception:
            mounted = False
        # Ne jamais exposer le mot de passe
        safe_m = {k: v for k, v in m.items() if k != "password"}
        result.append({**safe_m, "mounted": mounted})
    return result


@router.get("/browse")
async def browse(path: str = "/opt/audiobox/nas"):
    """Parcourt un répertoire NAS monté."""
    # Résoudre les symlinks et .. pour éviter les traversals
    try:
        p = Path(path).resolve()
    except Exception:
        raise HTTPException(status_code=400, detail="Chemin invalide")

    if not _is_safe_path(str(p)):
        raise HTTPException(status_code=403, detail="Accès refusé — chemin hors zone autorisée")

    if not p.exists():
        raise HTTPException(status_code=404, detail=f"Chemin introuvable: {path}")

    if not p.is_dir():
        raise HTTPException(status_code=400, detail="Ce chemin n'est pas un répertoire")

    items = []
    try:
        for entry in sorted(p.iterdir()):
            try:
                stat = entry.stat()
                items.append({
                    "name":   entry.name,
                    "path":   str(entry),
                    "is_dir": entry.is_dir(),
                    "size":   stat.st_size if entry.is_file() else 0,
                    "ext":    entry.suffix.lower() if entry.is_file() else "",
                })
            except PermissionError:
                continue
            except Exception:
                continue
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission refusée sur ce répertoire")

    return {"path": str(p), "items": items, "count": len(items)}
