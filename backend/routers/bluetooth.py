from fastapi import APIRouter, HTTPException
import asyncio, re, shutil, logging, subprocess

router = APIRouter(prefix="/bluetooth", tags=["bluetooth"])
logger = logging.getLogger("bluetooth")

_scan_proc = None  # Processus de scan en cours

MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


def _require_bluetoothctl():
    if not shutil.which("bluetoothctl"):
        raise HTTPException(status_code=503,
            detail="bluetoothctl non disponible")


def _validate_mac(mac: str):
    if not MAC_RE.match(mac):
        raise HTTPException(status_code=400, detail=f"Adresse MAC invalide: {mac}")


async def _bt_cmd(cmd: str, timeout: int = 10) -> str:
    """Exécute une commande bluetoothctl unique via --timeout."""
    _require_bluetoothctl()
    try:
        proc = await asyncio.create_subprocess_exec(
            "bluetoothctl", *cmd.split(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return stdout.decode(errors="replace")
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        return ""
    except Exception as e:
        logger.error(f"bluetoothctl error: {e}")
        return ""


@router.get("/devices")
async def list_devices():
    """Liste les périphériques Bluetooth connus."""
    _require_bluetoothctl()
    output = await _bt_cmd("devices", timeout=5)
    devices = []
    for line in output.splitlines():
        m = re.match(r"Device ([0-9A-Fa-f:]{17}) (.+)", line)
        if not m:
            continue
        mac, name = m.group(1), m.group(2).strip()
        info = await _bt_cmd(f"info {mac}", timeout=5)
        devices.append({
            "mac":       mac,
            "name":      name,
            "connected": "Connected: yes" in info,
            "paired":    "Paired: yes" in info,
            "trusted":   "Trusted: yes" in info,
        })
    return devices


@router.post("/scan")
async def start_scan():
    """Scan Bluetooth via hcitool — plus stable que bluetoothctl scan."""
    _require_bluetoothctl()
    try:
        # Activer le scan via hciconfig d'abord
        subprocess.run(["hciconfig", "hci0", "up"],
                       capture_output=True, timeout=3)

        # Utiliser bluetoothctl avec timeout intégré
        proc = await asyncio.create_subprocess_exec(
            "bluetoothctl",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        # Envoyer les commandes et attendre
        commands = b"scan on\n"
        try:
            await asyncio.wait_for(
                asyncio.sleep(8),  # Scanner 8 secondes
                timeout=25
            )
        except asyncio.TimeoutError:
            pass

        # Arrêter proprement
        try:
            proc.stdin.write(b"scan off\nquit\n")
            await proc.stdin.drain()
            await asyncio.wait_for(proc.communicate(b""), timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    except Exception as e:
        logger.warning(f"Scan error (non bloquant): {e}")

    # Retourner les appareils trouvés
    return await list_devices()


@router.post("/pair/{mac}")
async def pair_device(mac: str):
    _validate_mac(mac)
    # Pair
    out = await _bt_cmd(f"pair {mac}", timeout=30)
    if "Failed to pair" in out or "not available" in out:
        raise HTTPException(status_code=500,
            detail=f"Échec du jumelage: {out[:200]}")
    # Trust
    await _bt_cmd(f"trust {mac}", timeout=5)
    # Connect
    out = await _bt_cmd(f"connect {mac}", timeout=15)
    if "Failed to connect" in out:
        raise HTTPException(status_code=500,
            detail=f"Jumelé mais connexion échouée: {out[:200]}")
    return {"status": "paired_and_connected", "mac": mac}


@router.post("/connect/{mac}")
async def connect_device(mac: str):
    _validate_mac(mac)
    out = await _bt_cmd(f"connect {mac}", timeout=15)
    if "Failed to connect" in out:
        raise HTTPException(status_code=500, detail=out[:200])
    return {"status": "connected", "mac": mac}


@router.post("/disconnect/{mac}")
async def disconnect_device(mac: str):
    _validate_mac(mac)
    await _bt_cmd(f"disconnect {mac}", timeout=5)
    return {"status": "disconnected", "mac": mac}


@router.delete("/remove/{mac}")
async def remove_device(mac: str):
    _validate_mac(mac)
    await _bt_cmd(f"remove {mac}", timeout=5)
    return {"status": "removed", "mac": mac}
