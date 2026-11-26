import asyncio, json, os, shutil, logging
from pathlib import Path

MPV_SOCKET = "/tmp/jv-mpv.sock"
# Les messages de mpv vont dans ce fichier (vidé à chaque lecture). Avant, ils allaient
# dans un tuyau que personne ne lisait : plein, il aurait bloqué mpv.
MPV_JOURNAL = "/tmp/jv-mpv.log"
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
        self._num = 0         # numéro des demandes envoyées à mpv
        self._verrou = asyncio.Lock()
        self._connexions = asyncio.Semaphore(4)
        self._connu: dict = {}  # dernière position et durée lues

    # ── Vérifications ────────────────────────────────────────────────────────

    def _check_mpv(self):
        if not shutil.which("mpv"):
            raise RuntimeError("mpv non installé — sudo apt-get install mpv")

    # ── Playback ──────────────────────────────────────────────────────────────

    async def play(self, uri: str, output: str = "jack", start_time: float = 0.0,
                   http_token: str = "", vitesse: float = 1.0, en_pause: bool = False):
        """en_pause : chargé mais en pause (reprise d'un livre qui était en pause)."""
        self._check_mpv()
        # Une seule mise en route à la fois. Avant, deux appuis rapprochés (ou l'écran et
        # Home Assistant ensemble) lançaient deux mpv : l'un des deux jouait sans qu'on
        # puisse plus l'arrêter.
        async with self._verrou:
            await self._lancer(uri, output, start_time, http_token, vitesse, en_pause)

    async def _lancer(self, uri: str, output: str, start_time: float,
                      http_token: str, vitesse: float, en_pause: bool):
        # Arrêt complet + délai pour s'assurer que mpv est bien terminé
        await self._arreter()
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
        if en_pause:
            cmd.append("--pause")
        # « -- » : tout ce qui suit est un fichier, jamais une option. Sans lui, une
        # adresse commençant par « --script=… » aurait été comprise comme une option.
        cmd.append("--")
        cmd.append(uri)

        env = os.environ.copy()
        # S'assurer que PipeWire est accessible
        uid = os.getuid()
        env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{uid}")
        env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path=/run/user/{uid}/bus")
        env.setdefault("PIPEWIRE_RUNTIME_DIR", f"/run/user/{uid}")

        try:
            journal = open(MPV_JOURNAL, "wb")
        except OSError:
            journal = asyncio.subprocess.DEVNULL
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=journal,
                env=env
            )
        except FileNotFoundError:
            raise RuntimeError("mpv introuvable dans le PATH")
        finally:
            if journal is not asyncio.subprocess.DEVNULL:
                journal.close()  # mpv garde sa propre copie

        self._current_uri = uri
        self._paused = en_pause
        self._connu = {}

        # Attendre que le socket IPC soit prêt (max 3s)
        for _ in range(30):
            if os.path.exists(MPV_SOCKET):
                break
            # Vérifier que mpv n'a pas planté immédiatement
            if self._proc.returncode is not None:
                try:
                    with open(MPV_JOURNAL, errors="replace") as f:
                        message = f.read()[:200]
                except OSError:
                    message = ""
                raise RuntimeError(f"mpv a quitté immédiatement: {message}")
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
        async with self._verrou:
            await self._arreter()

    async def _arreter(self):
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=3)
            except asyncio.TimeoutError:
                self._proc.kill()
                await self._proc.wait()
        self._proc = None
        self._paused = False
        self._connu = {}
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
                # Les trois questions sur UNE connexion (avant : trois connexions à chaque fois).
                pos_resp, dur_resp, pau_resp = await self._mpv_cmds([
                    {"command": ["get_property", "time-pos"]},
                    {"command": ["get_property", "duration"]},
                    {"command": ["get_property", "pause"]},
                ])
                # Une réponse manquante garde la dernière valeur connue, au lieu d'afficher 0.
                position = float(pos_resp.get("data") or 0) if pos_resp else self._connu.get("position", 0.0)
                duration = float(dur_resp.get("data") or 0) if dur_resp else self._connu.get("duration", 0.0)
                paused   = bool(pau_resp.get("data", False)) if pau_resp else self._paused
                self._paused = paused
                self._connu = {"position": position, "duration": duration}
            except Exception as e:
                logger.debug(f"mpv status error: {e}")
        elif not is_running:
            self._connu = {}

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
        return (await self._mpv_cmds([cmd]))[0]

    async def _mpv_cmds(self, cmds: list[dict]) -> list[dict]:
        """
        Envoie des commandes à mpv sur une seule connexion et rend LEURS réponses, dans l'ordre.

        mpv envoie aussi des événements (« pause », « playback-restart »…) sur la même
        connexion : chaque demande porte un numéro, et on range les réponses par numéro.
        Les numéros sont gardés à part pour CET appel : l'écran, l'appli, Home Assistant
        et la synchro ABS interrogent mpv en même temps. Avant (1.5), la comparaison se
        faisait avec le compteur commun, déjà avancé par une autre demande : la réponse
        était ignorée, on attendait 2 s pour rien et la position affichée tombait à 0.
        Au plus 4 connexions à la fois : au-delà, mpv refusait les suivantes.
        """
        vides = [{} for _ in cmds]
        if not os.path.exists(MPV_SOCKET):
            return vides
        nums = []
        lignes = []
        for cmd in cmds:
            self._num += 1
            nums.append(self._num)
            lignes.append(json.dumps(dict(cmd, request_id=self._num)))
        reponses: dict[int, dict] = {}
        async with self._connexions:
            for essai in range(3):
                writer = None
                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_unix_connection(MPV_SOCKET), timeout=2
                    )
                    writer.write(("\n".join(lignes) + "\n").encode())
                    await writer.drain()
                    attendues = set(nums)
                    for _ in range(50 + 10 * len(nums)):
                        if not attendues:
                            break
                        line = await asyncio.wait_for(reader.readline(), timeout=2)
                        if not line:
                            break
                        try:
                            rep = json.loads(line.decode())
                        except json.JSONDecodeError:
                            continue
                        rid = rep.get("request_id")
                        if rid in attendues:
                            reponses[rid] = rep
                            attendues.discard(rid)
                        elif len(nums) == 1 and "event" not in rep and rid is None and "error" in rep:
                            reponses[nums[0]] = rep      # très vieux mpv, sans numéro
                            attendues.clear()
                    break
                except (BlockingIOError, ConnectionRefusedError, FileNotFoundError):
                    # mpv occupé ou en train de démarrer : on réessaie un instant après.
                    await asyncio.sleep(0.05 * (essai + 1))
                except (asyncio.TimeoutError, OSError):
                    break
                finally:
                    if writer is not None:
                        writer.close()
                        try:
                            await writer.wait_closed()
                        except Exception:
                            pass
        return [reponses.get(n, {}) for n in nums]

    async def _resolve_sink(self, output: str) -> str:
        """La sortie audio : la sortie par défaut de PipeWire (jack ou HDMI)."""
        return "auto"
