from pydantic import BaseModel
from typing import Optional


class SessionEntry(BaseModel):
    session_key: str
    session_id: str
    agent_id: str = "default"
    updated_at: int
    session_data: dict
    channel: Optional[str] = None
    label: Optional[str] = None


class PruneRequest(BaseModel):
    agent_id: str = "default"
    max_age_ms: int = 2592000000  # 30 days


class CapRequest(BaseModel):
    agent_id: str = "default"
    max_count: int = 500
