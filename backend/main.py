from fastapi import FastAPI, Depends, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from .auth import router as auth_router, get_current_user_token, user_refresh_tokens
from .models import GenerateNotesRequest, GenerateNotesResponse
from .services.gemini import generate_notes
from .services.drive import upload_to_drive
import os
import requests

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all for extension
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)

def get_video_title(video_url: str) -> str:
    # Basic oEmbed or scraping to get title. 
    # For robust usage, use YouTube API or handle failure gracefully.
    # Fallback to "Note-<timestamp>" if fails.
    try:
        if "youtube.com" in video_url or "youtu.be" in video_url:
            oembed_url = f"https://www.youtube.com/oembed?url={video_url}&format=json"
            resp = requests.get(oembed_url)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("title", "Untitled Video")
    except:
        pass
    return "YouTube Note"

@app.post("/generate-notes", response_model=GenerateNotesResponse)
async def generate_notes_endpoint(
    request: GenerateNotesRequest,
    user: dict = Depends(get_current_user_token)
):
    google_id = user.get("sub")
    if not google_id or google_id not in user_refresh_tokens:
        raise HTTPException(status_code=401, detail="User not authenticated or session expired. Please login again.")
    
    refresh_token = user_refresh_tokens[google_id]
    
    # 1. Generate Notes
    try:
        notes_content = generate_notes(request.videoUrl)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gemini generation failed: {str(e)}")
    
    # 2. Get Video Title
    video_title = get_video_title(request.videoUrl)
    
    # 3. Upload to Drive
    try:
        drive_link = upload_to_drive(refresh_token, notes_content, video_title)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Drive upload failed: {str(e)}")
        
    return GenerateNotesResponse(driveUrl=drive_link)
