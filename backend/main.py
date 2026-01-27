from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
import asyncio
import json
import logging
import datetime

from .auth import router as auth_router, get_current_user
from .models import GenerateNotesRequest, GenerateNotesResponse, NoteStatus
from .services.gemini import generate_notes
from .services.gcs import upload_note, get_note_content, save_note_metadata, get_note_metadata
import requests

app = FastAPI()

@app.middleware("http")
async def log_origin(request: Request, call_next):
    origin = request.headers.get("origin")
    logger.info(f"Incoming request from origin: {origin}")
    response = await call_next(request)
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://www.youtube.com"], 
    allow_origin_regex=r"https://.*\.youtube\.com", # Allow all youtube subdomains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_video_title(video_url: str) -> str:
    try:
        if "youtube.com" in video_url or "youtu.be" in video_url:
            oembed_url = f"https://www.youtube.com/oembed?url={video_url}&format=json"
            resp = requests.get(oembed_url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("title", "Untitled Video")
    except Exception as e:
        logger.error(f"Error fetching video title: {e}")
    return "YouTube Note"

def background_generate_note(user_id: str, video_id: str, video_url: str):
    """
    Background task to generate note and upload to GCS.
    Updates GCS metadata status through the process.
    """
    try:
        # Fetch current metadata to preserve fields
        metadata = get_note_metadata(user_id, video_id)
        if not metadata:
             logger.error(f"Metadata not found for starting background task {user_id} {video_id}")
             return

        # Update status to generating
        metadata["status"] = NoteStatus.GENERATING
        metadata["updated_at"] = datetime.datetime.utcnow().isoformat()
        save_note_metadata(user_id, video_id, metadata)

        # 1. Generate Content
        try:
            content = generate_notes(video_url)
        except Exception as e:
            logger.error(f"Gemini generation failed: {e}")
            metadata["status"] = NoteStatus.FAILED
            metadata["updated_at"] = datetime.datetime.utcnow().isoformat()
            save_note_metadata(user_id, video_id, metadata)
            return

        # 2. Upload to GCS
        try:
            gcs_key = upload_note(user_id, video_id, content)
        except Exception as e:
            logger.error(f"GCS upload failed: {e}")
            metadata["status"] = NoteStatus.FAILED
            metadata["updated_at"] = datetime.datetime.utcnow().isoformat()
            save_note_metadata(user_id, video_id, metadata)
            return

        # 3. Update Status to Ready
        metadata["gcs_object_key"] = gcs_key
        metadata["status"] = NoteStatus.READY
        metadata["updated_at"] = datetime.datetime.utcnow().isoformat()
        
        save_note_metadata(user_id, video_id, metadata)
        logger.info(f"Note generated successfully for user {user_id} video {video_id}")

    except Exception as e:
        logger.exception(f"Unexpected error in background task: {e}")
        # Try to set status to failed if possible
        try:
             metadata = get_note_metadata(user_id, video_id) or {}
             metadata["status"] = NoteStatus.FAILED
             metadata["updated_at"] = datetime.datetime.utcnow().isoformat()
             save_note_metadata(user_id, video_id, metadata)
        except:
            pass

@app.post("/generate-notes", response_model=GenerateNotesResponse)
async def generate_notes_endpoint(
    request: GenerateNotesRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user)
):
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    video_id = request.videoId
    if not video_id:
        # Fallback extraction (very basic)
        if "v=" in request.videoUrl:
            video_id = request.videoUrl.split("v=")[1].split("&")[0]
        else:
             raise HTTPException(status_code=400, detail="Could not extract video ID")

    video_title = get_video_title(request.videoUrl)

    # Init Metadata
    metadata = {
        "user_id": user_id,
        "video_id": video_id,
        "video_title": video_title,
        "status": NoteStatus.PENDING,
        "created_at": datetime.datetime.utcnow().isoformat(),
        "updated_at": datetime.datetime.utcnow().isoformat()
    }
    
    # Save Initial Metadata (Overwrites existing if any - intentional regeneration)
    save_note_metadata(user_id, video_id, metadata)
    
    background_tasks.add_task(background_generate_note, user_id, video_id, request.videoUrl)

    return GenerateNotesResponse(
        message="Note generation started",
        videoId=video_id
    )

@app.get("/notes/{video_id}/events")
async def note_events(
    video_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    SSE endpoint to stream status updates.
    """
    user_id = user.get("sub")
    
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break

            # Poll GCS Metadata
            # Note: Polling GCS frequently can involve costs/latency. 
            # 2 seconds interval is reasonable.
            metadata = get_note_metadata(user_id, video_id)
            status = metadata.get("status") if metadata else "unknown"
            
            data = json.dumps({"status": status})
            yield f"data: {data}\n\n"

            if status in [NoteStatus.READY, NoteStatus.FAILED]:
                break
            
            await asyncio.sleep(2) 

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/notes/{video_id}/download")
async def download_note(
    video_id: str,
    user: dict = Depends(get_current_user)
):
    user_id = user.get("sub")
    
    metadata = get_note_metadata(user_id, video_id)
    
    if not metadata or metadata.get("status") != NoteStatus.READY:
        raise HTTPException(status_code=404, detail="Note not ready or not found")
    
    # Use key from metadata or construct it standard way
    gcs_key = metadata.get("gcs_object_key") # or construct default
    if not gcs_key:
         # Fallback
         gcs_key = f"notes/user_{user_id}/{video_id}.md"

    try:
        content = get_note_content(gcs_key)
    except Exception as e:
        logger.error(f"Error fetching from GCS: {e}")
        raise HTTPException(status_code=500, detail="Error fetching note content")

    filename = f"{metadata.get('video_title', 'Note')}.md".replace("/", "-")
    return Response(
        content=content,
        media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\""}
    )
