from pydantic import BaseModel


class TranscriptEvent(BaseModel):
    session_id: str
    agent_id: str = "default"
    event_type: str
    event_data: dict


class TranscriptResponse(BaseModel):
    id: str
    session_id: str
    sequence_num: int
    event_type: str
    event_data: dict
    created_at: str
