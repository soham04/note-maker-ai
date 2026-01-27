from pydantic import BaseModel
from typing import Optional
import enum

class NoteStatus(str, enum.Enum):
    PENDING = "pending"
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"

class GenerateNotesRequest(BaseModel):
    videoUrl: str
    videoId: Optional[str] = None


class GenerateNotesResponse(BaseModel):
    message: str
    videoId: str

class User(BaseModel):
    google_id: str
    email: str
    name: str
    picture: Optional[str] = None
