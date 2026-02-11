from fastapi import APIRouter, Request, HTTPException
from typing import Optional

from ..models.memory import (
    MemorySearchRequest,
    StoreChunkRequest,
    RememberRequest,
    RecallRequest,
    FileSyncEntry,
)

router = APIRouter(prefix="/api/memory")


def _get_memory_service(request: Request):
    svc = request.app.state.memory_service
    if not svc:
        raise HTTPException(status_code=503, detail="Memory service not available")
    return svc


@router.post("/search")
async def search_memory(request: Request, body: MemorySearchRequest):
    svc = _get_memory_service(request)
    results = await svc.search(
        query=body.query,
        max_results=body.max_results,
        min_score=body.min_score,
        source=body.source,
        hybrid=body.hybrid,
    )
    return {"results": results, "count": len(results)}


@router.post("/chunks")
async def store_chunk(request: Request, body: StoreChunkRequest):
    svc = _get_memory_service(request)
    result = await svc.store_chunk(body.model_dump())
    return result


@router.post("/chunks/batch")
async def store_chunks_batch(request: Request, chunks: list[StoreChunkRequest]):
    svc = _get_memory_service(request)
    result = await svc.store_chunks_batch([c.model_dump() for c in chunks])
    return result


@router.delete("/chunks/{chunk_id}")
async def delete_chunk(request: Request, chunk_id: str):
    svc = _get_memory_service(request)
    result = await svc.delete_chunk(chunk_id)
    return result


@router.post("/files/sync")
async def sync_files(request: Request, files: list[FileSyncEntry]):
    svc = _get_memory_service(request)
    result = await svc.sync_files([f.model_dump() for f in files])
    return result


@router.get("/status")
async def memory_status(request: Request):
    svc = _get_memory_service(request)
    return await svc.get_status()


# ---- Long-term memory endpoints ----

@router.post("/remember")
async def remember(request: Request, body: RememberRequest):
    svc = _get_memory_service(request)
    result = await svc.remember(
        text=body.text,
        agent_id=body.agent_id,
        importance=body.importance,
        category=body.category,
    )
    return result


@router.post("/recall")
async def recall(request: Request, body: RecallRequest):
    svc = _get_memory_service(request)
    results = await svc.recall(
        query=body.query,
        agent_id=body.agent_id,
        max_results=body.max_results,
        min_score=body.min_score,
    )
    return {"results": results, "count": len(results)}


@router.delete("/forget/{memory_id}")
async def forget(request: Request, memory_id: str):
    svc = _get_memory_service(request)
    result = await svc.forget(memory_id)
    return result


@router.get("/count")
async def count_memories(request: Request, agent_id: str = "default"):
    svc = _get_memory_service(request)
    return await svc.count_memories(agent_id)
