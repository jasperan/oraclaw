from pydantic import BaseModel, Field
from typing import Optional


class MemorySearchRequest(BaseModel):
    query: str
    max_results: int = 6
    min_score: float = 0.3
    source: Optional[str] = None
    hybrid: bool = True


class MemorySearchResult(BaseModel):
    path: str
    start_line: int = Field(alias="startLine", default=0)
    end_line: int = Field(alias="endLine", default=0)
    score: float
    snippet: str
    source: str = "memory"
    citation: Optional[str] = None

    model_config = {"populate_by_name": True}


class StoreChunkRequest(BaseModel):
    id: str
    path: str
    source: str = "memory"
    start_line: int
    end_line: int
    hash: str
    model: str
    text: str


class RememberRequest(BaseModel):
    text: str
    agent_id: str = "default"
    importance: float = 0.7
    category: str = "other"


class RecallRequest(BaseModel):
    query: str
    agent_id: str = "default"
    max_results: int = 5
    min_score: float = 0.3


class FileSyncEntry(BaseModel):
    file_id: str
    path: str
    source: str = "memory"
    hash: Optional[str] = None
    chunk_count: int = 0


class MemoryStatusResponse(BaseModel):
    chunk_count: int = 0
    file_count: int = 0
    memory_count: int = 0
    cache_count: int = 0
