from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
from sqlalchemy.orm import Session
import asyncio
import json
import logging
import datetime

from backend.auth import router as auth_router, get_current_user
from backend.models import GenerateNotesRequest, GenerateNotesResponse
from backend.db_models import NoteStatus
from backend.services.gemini import generate_notes
from backend.services.gcs import upload_note, get_note_content
from backend.services import db as db_service
from backend.database import engine, Base, get_db
import requests

# Create Tables
Base.metadata.create_all(bind=engine)

app = FastAPI()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

def background_generate_note(db: Session, note_id: int, user_id: str, video_id: str, video_url: str):
    """
    Background task to generate note and upload to GCS.
    Updates DB status through the process.
    """
    try:
        # Update status to generating
        db_service.update_note_status(db, note_id, NoteStatus.GENERATING)

        # 1. Generate Content
        try:
            content = generate_notes(video_url)
        except Exception as e:
            logger.error(f"Gemini generation failed: {e}")
            db_service.update_note_status(db, note_id, NoteStatus.FAILED)
            return

        # 2. Upload to GCS
        try:
            gcs_key = upload_note(user_id, video_id, content)
        except Exception as e:
            logger.error(f"GCS upload failed: {e}")
            db_service.update_note_status(db, note_id, NoteStatus.FAILED)
            return

        # 3. Update Status to Ready
        db_service.update_note_status(db, note_id, NoteStatus.READY, gcs_key)
        
        logger.info(f"Note generated successfully for user {user_id} video {video_id}")

    except Exception as e:
        logger.exception(f"Unexpected error in background task: {e}")
        try:
             db_service.update_note_status(db, note_id, NoteStatus.FAILED)
        except:
            pass
    finally:
        db.close() # Important for background tasks in a separate thread context if manually managed, 
                   # but here we used a fresh session typically or need to be careful. 
                   # Simplest is to pass a new session generator or handle it.
                   # Actually, Dependency injection sessions are closed after request.
                   # For background tasks, we need a fresh session.
        pass

# Wrapper for background task to manage session
def run_background_generate_task(note_id: int, user_id: str, video_id: str, video_url: str):
    db = next(get_db())
    try:
        background_generate_note(db, note_id, user_id, video_id, video_url)
    finally:
        db.close()

@app.post("/generate-notes", response_model=GenerateNotesResponse)
async def generate_notes_endpoint(
    request: GenerateNotesRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user_id = user.get("sub")
    email = user.get("email")
    
    # Ensure user exists in DB (syncing local DB with Auth info)
    db_user = db_service.get_or_create_user(db, user_id, email)

    video_id = request.videoId
    if not video_id:
        if "v=" in request.videoUrl:
            video_id = request.videoUrl.split("v=")[1].split("&")[0]
        else:
             raise HTTPException(status_code=400, detail="Could not extract video ID")

    video_title = get_video_title(request.videoUrl)

    # Create Initial Note Record
    note = db_service.create_note(db, db_user.id, video_id, video_title)
    
    background_tasks.add_task(run_background_generate_task, note.id, str(db_user.id), video_id, request.videoUrl)

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
        # Create a new DB session for polling since this is a long running generator 
        # and we don't want to hold the request session or share it improperly
        while True:
            if await request.is_disconnected():
                break

            # Poll DB
            db = next(get_db())
            try:
                db_user = db_service.get_user_by_google_id(db, user_id)
                if not db_user:
                     yield f"data: {json.dumps({'status': 'error'})}\n\n"
                     break
                     
                note = db_service.get_note(db, db_user.id, video_id)
                status = note.status if note else "unknown"
                
                data = json.dumps({"status": status})
                yield f"data: {data}\n\n"

                if status in [NoteStatus.READY, NoteStatus.FAILED]:
                    break
            finally:
                db.close()
            
            await asyncio.sleep(2) 

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/notes/{video_id}/download")
async def download_note(
    video_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user_id = user.get("sub")
    
    db_user = db_service.get_user_by_google_id(db, user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    note = db_service.get_note(db, db_user.id, video_id)
    
    if not note or note.status != NoteStatus.READY:
        raise HTTPException(status_code=404, detail="Note not ready or not found")
    
    gcs_key = note.gcs_object_key
    if not gcs_key:
         # Fallback logic should ideally not happen if status is READY
         gcs_key = f"notes/user_{db_user.id}/{video_id}.md"

    try:
        content = get_note_content(gcs_key)
    except Exception as e:
        logger.error(f"Error fetching from GCS: {e}")
        raise HTTPException(status_code=500, detail="Error fetching note content")

    filename = f"{note.video_title or 'Note'}.md".replace("/", "-")
    return Response(
        content=content,
        media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\""}
    )

@app.on_event("shutdown")
def shutdown():
    connector.close()
