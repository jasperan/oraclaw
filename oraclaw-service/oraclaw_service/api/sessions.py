from fastapi import APIRouter, Request, HTTPException

from ..models.sessions import SessionEntry, PruneRequest, CapRequest

router = APIRouter(prefix="/api/sessions")


def _get_session_service(request: Request):
    svc = request.app.state.session_service
    if not svc:
        raise HTTPException(status_code=503, detail="Session service not available")
    return svc


@router.get("/")
async def list_sessions(request: Request, agent_id: str = "default"):
    svc = _get_session_service(request)
    sessions = await svc.get_sessions(agent_id)
    return {"sessions": sessions, "count": len(sessions)}


@router.get("/{session_key}")
async def get_session(request: Request, session_key: str):
    svc = _get_session_service(request)
    session = await svc.get_session(session_key)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.put("/")
async def upsert_session(request: Request, body: SessionEntry):
    svc = _get_session_service(request)
    result = await svc.upsert_session(body.model_dump())
    return result


@router.patch("/{session_key}")
async def update_session(request: Request, session_key: str, updates: dict):
    svc = _get_session_service(request)
    result = await svc.update_session(session_key, updates)
    return result


@router.delete("/{session_key}")
async def delete_session(request: Request, session_key: str):
    svc = _get_session_service(request)
    result = await svc.delete_session(session_key)
    return result


@router.post("/prune")
async def prune_sessions(request: Request, body: PruneRequest):
    svc = _get_session_service(request)
    result = await svc.prune_stale(agent_id=body.agent_id, max_age_ms=body.max_age_ms)
    return result


@router.post("/cap")
async def cap_sessions(request: Request, body: CapRequest):
    svc = _get_session_service(request)
    result = await svc.cap_count(agent_id=body.agent_id, max_count=body.max_count)
    return result
