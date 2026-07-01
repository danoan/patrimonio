import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.db import create_db_and_tables
from app.routers import (
    acoes,
    acoes_us,
    configuracoes,
    contas,
    divisao,
    ir,
    locale,
    movimentos,
    overview,
    projecao,
    recorrentes,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    create_db_and_tables()
    logger.info("Database ready")
    yield


app = FastAPI(title="Patrimônio", docs_url=None, redoc_url=None, lifespan=lifespan)

# Static files
static_path = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# Register routers
app.include_router(overview.router)
app.include_router(movimentos.router)
app.include_router(recorrentes.router)
app.include_router(contas.router)
app.include_router(acoes.router)
app.include_router(acoes_us.router)
app.include_router(divisao.router)
app.include_router(projecao.router)
app.include_router(ir.router)
app.include_router(configuracoes.router)
app.include_router(locale.router)
