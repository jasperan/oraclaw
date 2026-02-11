from fastapi import APIRouter, Request, HTTPException

from ..models.transcripts import TranscriptEvent

router = APIRouter(prefix="/api/transcripts")


def _get_transcript_service(request: Request):
    svc = request.app.state.transcript_service
    if not svc:
        raise HTTPException(status_code=503, detail="Transcript service not available")
    return svc


@router.post("/")
async def append_event(request: Request, body: TranscriptEvent):
    svc = _get_transcript_service(request)
    result = await svc.append(
        session_id=body.session_id,
        agent_id=body.agent_id,
        event_type=body.event_type,
        event_data=body.event_data,
    )
    return result


@router.get("/{session_id}")
async def get_events(request: Request, session_id: str, offset: int = 0, limit: int = 100):
    svc = _get_transcript_service(request)
    events = await svc.get_events(session_id, offset=offset, limit=limit)
    return {"events": events, "count": len(events)}


@router.get("/{session_id}/header")
async def get_header(request: Request, session_id: str):
    svc = _get_transcript_service(request)
    header = await svc.get_header(session_id)
    if not header:
        raise HTTPException(status_code=404, detail="Session header not found")
    return header


@router.delete("/{session_id}")
async def delete_transcript(request: Request, session_id: str):
    svc = _get_transcript_service(request)
    result = await svc.delete_session(session_id)
    return result
