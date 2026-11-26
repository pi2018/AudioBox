import logging
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from pathlib import Path
from routers import abs, player, youtube, nas, settings, system, public_api, podcast
from services.ws_manager import WSManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("main")

ws_manager = WSManager()
FRONTEND_DIR = Path("/opt/jv/frontend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Générer le token dès le démarrage. Il n'est JAMAIS écrit dans le journal :
    # le journal est lisible par d'autres programmes, et l'était même depuis le réseau.
    try:
        from routers.settings import _get_token, TOKEN_FILE
        _get_token()
        logger.info(f"AudioBox {system.VERSION_EN_COURS} — token prêt (fichier {TOKEN_FILE})")
    except Exception as e:
        logger.error(f"Impossible de générer le token: {e}")
    app.state.ws_manager = ws_manager
    yield
    logger.info("AudioBox arrêté")


app = FastAPI(
    title="AudioBox API",
    version=system.VERSION_EN_COURS,
    description="Backend AudioBox — Audiobookshelf, Radios, YouTube, NAS",
    lifespan=lifespan
)

# Pas de CORS : l'interface est servie par ce même serveur (même origine).
# Avant, « allow_origins=* » laissait n'importe quel site web ouvert dans un
# navigateur de la maison piloter la box.


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Erreur non gérée sur {request.url}: {exc}")
    return JSONResponse(status_code=500, content={"detail": "Erreur interne du serveur"})


for router in [abs.router, player.router, youtube.router,
               nas.router, settings.router, system.router, public_api.router,
               podcast.router]:
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
