from sqlalchemy.orm import Session
from .. import db_models
from ..db_models import NoteStatus
import datetime

def get_user_by_google_id(db: Session, google_id: str):
    return db.query(db_models.User).filter(db_models.User.google_id == google_id).first()

def create_user(db: Session, google_id: str, email: str, name: str = None):
    db_user = db_models.User(google_id=google_id, email=email, name=name)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def get_or_create_user(db: Session, google_id: str, email: str):
    user = get_user_by_google_id(db, google_id)
    if not user:
        user = create_user(db, google_id=google_id, email=email)
    return user

def get_note(db: Session, user_id: int, video_id: str):
    return db.query(db_models.Note).filter(
        db_models.Note.user_id == user_id,
        db_models.Note.video_id == video_id
    ).first()

def create_note(db: Session, user_id: int, video_id: str, video_title: str):
    # Check if exists, if so return it (will be updated) or delete and recreate?
    # Logic: "Regenerating notes overwrites the previous version"
    # We can update the existing record to PENDING.
    
    note = get_note(db, user_id, video_id)
    if note:
        note.status = NoteStatus.PENDING
        note.video_title = video_title
        note.updated_at = datetime.datetime.utcnow()
    else:
        note = db_models.Note(
            user_id=user_id,
            video_id=video_id,
            video_title=video_title,
            status=NoteStatus.PENDING
        )
        db.add(note)
    
    db.commit()
    db.refresh(note)
    return note

def update_note_status(db: Session, note_id: int, status: str, gcs_key: str = None):
    note = db.query(db_models.Note).filter(db_models.Note.id == note_id).first()
    if note:
        note.status = status
        if gcs_key:
            note.gcs_object_key = gcs_key
        note.updated_at = datetime.datetime.utcnow()
        db.commit()
        db.refresh(note)
    return note
