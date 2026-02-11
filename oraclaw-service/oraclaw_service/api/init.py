import logging

from fastapi import APIRouter, Request, HTTPException

from ..db.schema import init_schema

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/init")
async def initialize(request: Request):
    pool = request.app.state.pool
    embedding_service = request.app.state.embedding_service

    if not pool:
        raise HTTPException(status_code=503, detail="Database pool not available")

    # 1. Create tables and indexes
    schema_result = await init_schema(pool)
    logger.info("Schema init result: %s", schema_result)

    # 2. Load ONNX model if not present
    onnx_loaded = False
    if embedding_service:
        try:
            already_loaded = await embedding_service.check_onnx_loaded()
            if not already_loaded:
                await embedding_service.load_onnx_model()
                onnx_loaded = True
                logger.info("ONNX model loaded successfully")
            else:
                onnx_loaded = True
                logger.info("ONNX model already loaded")
        except Exception as e:
            logger.warning("ONNX model loading skipped: %s", e)

    # 3. Initialize embedding service
    if embedding_service and onnx_loaded:
        try:
            await embedding_service.initialize()
            logger.info("Embedding service initialized")
        except Exception as e:
            logger.warning("Embedding service initialization skipped: %s", e)

    return {
        "status": "initialized",
        "tables_created": schema_result.get("tables_created", []),
        "indexes_created": schema_result.get("indexes_created", []),
        "errors": schema_result.get("errors", []),
        "onnx_loaded": onnx_loaded,
    }
