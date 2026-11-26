import asyncio, json, os, shutil, logging
from pathlib import Path

MPV_SOCKET = "/tmp/jv-mpv.sock"
logger = logging.getLogger("audio_manager")


class AudioManager:
    def __init__(self):
        self._proc: asyncio.subprocess.Process | None = None
        self._current_uri  = ""
        self._current_title = ""
        self._volume = 80
        self._paused = False
        self._eq_filter = ""  # Filtre égaliseur actif
        self.vitesse = 1.0    # retenue d'un livre à l'autre

    # ── Vérifications ────────────────────────────────────────────────────────

    def _check_mpv(self):
        if not shutil.which("mpv"):
            raise RuntimeError("mpv non installé — sudo apt-get install mpv")

    # ── Playback ──────────────────────────────────────────────────────────────

    async def play(self, uri: str, output: str = "jack", start_time: float = 0.0,
                   http_token: str = "", vitesse: float = 1.0):
        self._check_mpv()
        # Arrêt complet + délai pour s'assurer que mpv est bien terminé
        await self.stop()
        await asyncio.sleep(0.5)
        logger.info(f"Lancement mpv: uri={uri[:60]} start={start_time:.1f}s")
        sink = await self._resolve_sink(output)

        cmd = [
            "mpv",
            "--no-video",
            "--input-ipc-server=" + MPV_SOCKET,
            f"--volume={self._volume}",
            "--really-quiet",
        ]
        # Sortie audio : ne passer --audio-device que si différent de auto
        if sink != "auto":
            cmd.append(f"--audio-device={sink}")

        # Token HTTP pour ABS
        if http_token:
            cmd.append(f"--http-header-fields=Authorization: Bearer {http_token}")

        # Égaliseur
        if self._eq_filter and self._eq_filter != "anull":
            cmd.append(f"--af={self._eq_filter}")

        if start_time > 0:
            cmd.append(f"--start={start_time}")
        if vitesse and abs(vitesse - 1.0) > 0.01:
            cmd.append(f"--speed={vitesse}")
        # « -- » : tout ce qui suit est un fichier, jamais une option. Sans lui, une
        # adresse commençant par « --script=… » aurait été comprise comme une option.
        cmd.append("--")
        cmd.append(uri)

        import os
        env = os.environ.copy()
        # S'assurer que PipeWire est accessible
        uid = os.getuid()
        env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{uid}")
        env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path=/run/user/{uid}/bus")
        env.setdefault("PIPEWIRE_RUNTIME_DIR", f"/run/user/{uid}")

        try:
            self._proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
        except FileNotFoundError:
            raise RuntimeError("mpv introuvable dans le PATH")

        self._current_uri = uri
        self._paused = False

        # Attendre que le socket IPC soit prêt (max 3s)
        for _ in range(30):
            if os.path.exists(MPV_SOCKET):
                break
            # Vérifier que mpv n'a pas planté immédiatement
            if self._proc.returncode is not None:
                stderr = await self._proc.stderr.read()
                raise RuntimeError(f"mpv a quitté immédiatement: {stderr.decode()[:200]}")
            await asyncio.sleep(0.1)

    async def pause(self):
        result = await self._mpv_cmd({"command": ["set_property", "pause", True]})
        if result:
            self._paused = True

    async def resume(self):
        result = await self._mpv_cmd({"command": ["set_property", "pause", False]})
        if result:
            self._paused = False

    async def stop(self):
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=3)
            except asyncio.TimeoutError:
                self._proc.kill()
                await self._proc.wait()
        self._proc = None
        self._paused = False
        # Nettoyer le socket
        try:
            if os.path.exists(MPV_SOCKET):
                os.unlink(MPV_SOCKET)
        except OSError:
            pass

    async def seek(self, position: float):
        if position < 0:
            position = 0.0
        await self._mpv_cmd({"command": ["seek", position, "absolute"]})

    async def set_volume(self, level: int):
        self._volume = max(0, min(100, level))
        await self._mpv_cmd({"command": ["set_property", "volume", self._volume]})

    async def set_speed(self, speed: float):
        """Règle la vitesse de lecture mpv (retenue pour le livre suivant)."""
        self.vitesse = speed
        await self._mpv_cmd({"command": ["set_property", "speed", speed]})

    async def set_equalizer(self, af_filter: str):
        """Applique un filtre audio à mpv en temps réel."""
        self._eq_filter = af_filter
        # Appliquer en temps réel si mpv tourne
        if os.path.exists(MPV_SOCKET):
            await self._mpv_cmd({"command": ["set_property", "af", af_filter]})

    # ── Status ────────────────────────────────────────────────────────────────

    async def get_status(self) -> dict:
        is_running = self._proc is not None and self._proc.returncode is None
        position = 0.0
        duration = 0.0
        paused   = self._paused

        if is_running and os.path.exists(MPV_SOCKET):
            try:
                pos_resp = await self._mpv_cmd({"command": ["get_property", "time-pos"]})
                dur_resp = await self._mpv_cmd({"command": ["get_property", "duration"]})
                pau_resp = await self._mpv_cmd({"command": ["get_property", "pause"]})
                position = float(pos_resp.get("data") or 0)
                duration = float(dur_resp.get("data") or 0)
                paused   = bool(pau_resp.get("data", False))
                self._paused = paused
            except Exception as e:
                logger.debug(f"mpv status error: {e}")

        return {
            "playing":  is_running and not paused,
            "paused":   paused,
            "stopped":  not is_running,
            "uri":      self._current_uri,
            "position": round(position, 1),
            "duration": round(duration, 1),
            "volume":   self._volume,
            "progress": round(position / duration * 100, 1) if duration > 0 else 0,
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _mpv_cmd(self, cmd: dict) -> dict:
        """
        Envoie une commande à mpv et rend SA réponse.

        mpv envoie aussi des événements (« pause », « playback-restart »…) sur la même
        connexion. Avant, la première ligne lue était prise pour la réponse : un
        événement passait parfois à sa place, et la position affichée retombait à 0.
        On numérote la demande et on attend la ligne qui porte ce numéro.
        """
        if not os.path.exists(MPV_SOCKET):
            return {}
        self._num = getattr(self, "_num", 0) + 1
        demande = dict(cmd, request_id=self._num)
        writer = None
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_unix_connection(MPV_SOCKET), timeout=2
            )
            writer.write((json.dumps(demande) + "\n").encode())
            await writer.drain()
            for _ in range(50):
                line = await asyncio.wait_for(reader.readline(), timeout=2)
                if not line:
                    return {}
                try:
                    rep = json.loads(line.decode())
                except json.JSONDecodeError:
                    continue
                if rep.get("request_id") == self._num or ("error" in rep and "event" not in rep and "request_id" not in rep):
                    return rep
            return {}
        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
            return {}
        finally:
            if writer is not None:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass

    async def _resolve_sink(self, output: str) -> str:
        """La sortie audio : la sortie par défaut de PipeWire (jack ou HDMI)."""
        return "auto"
