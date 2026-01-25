from pydantic import BaseModel
from typing import Optional

class GenerateNotesRequest(BaseModel):
    videoUrl: str
    videoId: Optional[str] = None

class GenerateNotesResponse(BaseModel):
    driveUrl: str

class User(BaseModel):
    google_id: str
    email: str
    name: str
    picture: Optional[str] = None
