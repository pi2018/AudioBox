from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import asyncio, json, shutil, logging

router = APIRouter(prefix="/youtube", tags=["youtube"])
logger = logging.getLogger("youtube")


def _require_ytdlp():
    if not shutil.which("yt-dlp"):
        raise HTTPException(
            status_code=503,
            detail="yt-dlp non installé. Lancez: sudo curl -sSL https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp && sudo chmod +x /usr/local/bin/yt-dlp"
        )


class YoutubeRequest(BaseModel):
    url: str
    audio_only: bool = True


async def _run_ytdlp(args: list, timeout: int = 30) -> str:
    """Lance yt-dlp et retourne stdout, lève HTTPException en cas d'erreur."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "yt-dlp", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="yt-dlp timeout — vérifiez votre connexion")
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="yt-dlp introuvable")

    if proc.returncode != 0:
        err = stderr.decode(errors="replace")[:300]
        # Erreurs courantes avec message lisible
        if "Video unavailable" in err or "This video is not available" in err:
            raise HTTPException(status_code=404, detail="Vidéo non disponible")
        if "Private video" in err:
            raise HTTPException(status_code=403, detail="Vidéo privée")
        if "age-restricted" in err.lower():
            raise HTTPException(status_code=403, detail="Vidéo avec restriction d'âge")
        raise HTTPException(status_code=400, detail=f"yt-dlp erreur: {err}")

    return stdout.decode(errors="replace").strip()


@router.post("/resolve")
async def resolve(req: YoutubeRequest):
    """Retourne l'URL de stream directe sans lancer la lecture."""
    _require_ytdlp()
    if not req.url:
        raise HTTPException(status_code=400, detail="URL manquante")

    fmt = "bestaudio/best" if req.audio_only else "best"
    raw = await _run_ytdlp([
        "--no-playlist",
        "--print", '{"url":"%(url)s","title":"%(title)s","duration":%(duration)s,"thumbnail":"%(thumbnail)s"}',
        "-f", fmt,
        req.url
    ])

    try:
        return json.loads(raw.splitlines()[0])
    except (json.JSONDecodeError, IndexError):
        raise HTTPException(status_code=500, detail="Impossible de parser la réponse yt-dlp")


@router.get("/search")
async def search_youtube(q: str, max_results: int = 10):
    """Recherche YouTube."""
    _require_ytdlp()
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="Requête de recherche vide")
    if max_results < 1 or max_results > 25:
        max_results = 10

    raw = await _run_ytdlp([
        f"ytsearch{max_results}:{q}",
        "--no-playlist",
        "--print", '{"id":"%(id)s","title":"%(title)s","duration":%(duration)s,"thumbnail":"%(thumbnail)s","url":"https://www.youtube.com/watch?v=%(id)s"}',
        "--skip-download"
    ], timeout=45)

    results = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            results.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return results
