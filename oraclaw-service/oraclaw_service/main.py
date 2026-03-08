import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .config import OraclawSettings
from .db.connection import OracleConnectionManager
from .db.schema import init_schema
from .services.embedding_service import EmbeddingService
from .services.memory_service import MemoryService
from .services.session_service import SessionService
from .services.transcript_service import TranscriptService
from .api import api_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = OraclawSettings()
    app.state.settings = settings

    conn_mgr = OracleConnectionManager(settings)
    try:
        pool = await conn_mgr.create_pool()
        app.state.pool = pool
        logger.info("Oracle connection pool created (min=%d, max=%d)", settings.oracle_pool_min, settings.oracle_pool_max)
    except Exception as e:
        logger.error("Failed to create Oracle connection pool: %s", e)
        app.state.pool = None
        pool = None

    # Initialize services
    # EmbeddingService uses synchronous connections (langchain-oracledb is sync)
    embedding_service = EmbeddingService(settings) if pool else None
    memory_service = MemoryService(pool, embedding_service, settings) if pool else None
    session_service = SessionService(pool) if pool else None
    transcript_service = TranscriptService(pool) if pool else None

    app.state.embedding_service = embedding_service
    app.state.memory_service = memory_service
    app.state.session_service = session_service
    app.state.transcript_service = transcript_service

    # Auto-init schema if configured
    if settings.auto_init and pool:
        try:
            result = await init_schema(pool)
            logger.info("Auto-init schema: %s", result)
            if embedding_service:
                try:
                    onnx_loaded = await embedding_service.check_onnx_loaded()
                    if not onnx_loaded:
                        await embedding_service.load_onnx_model()
                    await embedding_service.initialize()
                    if memory_service:
                        await memory_service.initialize()
                    logger.info("Services initialized successfully")
                except Exception as e:
                    logger.warning("Service initialization deferred: %s", e)
        except Exception as e:
            logger.warning("Auto-init failed (run POST /api/init manually): %s", e)

    yield

    # Shutdown
    if embedding_service:
        await embedding_service.close()
        logger.info("Embedding service connection released")
    if pool:
        await conn_mgr.close_pool()
        logger.info("Oracle connection pool closed")


app = FastAPI(
    title="OracLaw Service",
    version="0.1.0",
    description="Python sidecar for OracLaw - Oracle AI Vector Search powered code memory",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class BearerTokenMiddleware(BaseHTTPMiddleware):
    """Optional bearer token authentication.

    When ORACLAW_SERVICE_TOKEN is set, all requests must include
    a matching Authorization: Bearer <token> header.
    When not set, all requests are allowed (local dev mode).
    """

    async def dispatch(self, request: Request, call_next):
        token = request.app.state.settings.oraclaw_service_token
        if token:
            auth = request.headers.get("authorization", "")
            if not auth.startswith("Bearer ") or auth[7:] != token:
                return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
        return await call_next(request)


app.add_middleware(BearerTokenMiddleware)

app.include_router(api_router)


if __name__ == "__main__":
    import uvicorn

    settings = OraclawSettings()
    uvicorn.run(
        "oraclaw_service.main:app",
        host="0.0.0.0",
        port=settings.oraclaw_service_port,
        reload=True,
    )
