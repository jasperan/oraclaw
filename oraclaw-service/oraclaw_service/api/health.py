from fastapi import APIRouter, Request

from ..db.schema import check_tables_exist, get_schema_version

router = APIRouter()


@router.get("/api/health")
async def health(request: Request):
    pool = request.app.state.pool
    settings = request.app.state.settings
    embedding_service = request.app.state.embedding_service

    pool_info = {"min": 0, "max": 0, "busy": 0, "open": 0}
    if pool:
        pool_info = {
            "min": pool.min,
            "max": pool.max,
            "busy": pool.busy,
            "open": pool.opened,
        }

    tables = {}
    schema_version = "unknown"
    if pool:
        try:
            tables = await check_tables_exist(pool)
        except Exception:
            tables = {t: False for t in [
                "ORACLAW_META", "ORACLAW_FILES", "ORACLAW_CHUNKS",
                "ORACLAW_MEMORIES", "ORACLAW_EMBEDDING_CACHE",
                "ORACLAW_SESSIONS", "ORACLAW_TRANSCRIPTS", "ORACLAW_CONFIG",
            ]}
        try:
            schema_version = await get_schema_version(pool)
        except Exception:
            pass

    embedding_info = {"mode": None, "loaded": False}
    if embedding_service:
        embedding_info["mode"] = embedding_service.mode
        embedding_info["loaded"] = embedding_service.mode is not None
        try:
            embedding_info["onnx_in_db"] = await embedding_service.check_onnx_loaded()
        except Exception:
            embedding_info["onnx_in_db"] = False

    return {
        "status": "ok",
        "pool": pool_info,
        "onnx_model": {
            "name": settings.oracle_onnx_model,
            "loaded": embedding_info["loaded"],
            "mode": embedding_info.get("mode"),
        },
        "tables": tables,
        "schema_version": schema_version,
    }
