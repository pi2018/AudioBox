import logging
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from pathlib import Path
from routers import abs, player, youtube, nas, bluetooth, settings, spotify, system, public_api
from services.ws_manager import WSManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("main")

ws_manager = WSManager()
FRONTEND_DIR = Path("/opt/audiobox/frontend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Générer le token dès le démarrage et l'afficher dans les logs
    try:
        from routers.settings import _get_token
        token = _get_token()
        logger.info(f"=== AudioBox Dashboard Token: {token} ===")
    except Exception as e:
        logger.error(f"Impossible de générer le token: {e}")
    app.state.ws_manager = ws_manager
    yield
    logger.info("AudioBox arrêté")


app = FastAPI(
    title="AudioBox API",
    version="1.0.0",
    description="Backend AudioBox — Audiobookshelf, Radios, YouTube, NAS",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Erreur non gérée sur {request.url}: {exc}")
    return JSONResponse(status_code=500, content={"detail": "Erreur interne du serveur"})


for router in [abs.router, player.router, youtube.router,
               nas.router, bluetooth.router, settings.router, spotify.router,
               system.router, public_api.router]:
    app.include_router(router, prefix="/api")

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
else:
    logger.warning(f"Répertoire frontend introuvable: {FRONTEND_DIR}")

    @app.get("/")
    async def frontend_missing():
        return JSONResponse(
            status_code=503,
            content={"detail": f"Frontend introuvable dans {FRONTEND_DIR}"}
        )
