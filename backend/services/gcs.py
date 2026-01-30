from google.cloud import storage
import os
from dotenv import load_dotenv
import json

load_dotenv()

GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "yt-note-maker-notes")

# Initialize client. 
# Implicitly expects GOOGLE_APPLICATION_CREDENTIALS set or running in valid env.
try:
    storage_client = storage.Client()
except Exception as e:
    print(f"Warning: Could not init GCS client: {e}")
    storage_client = None

def get_bucket():
    if not storage_client:
        raise Exception("GCS Client not initialized")
    return storage_client.bucket(GCS_BUCKET_NAME)

def get_content_blob_name(user_id: str, video_id: str) -> str:
    return f"notes/user_{user_id}/{video_id}.md"

def upload_note(user_id: str, video_id: str, content: str) -> str:
    """
    Uploads note content to GCS.
    Returns the object key.
    Target path: notes/user_<user_id>/<video_id>.md
    """
    bucket = get_bucket()
    blob_name = get_content_blob_name(user_id, video_id)
    blob = bucket.blob(blob_name)
    
    blob.upload_from_string(content, content_type="text/markdown")
    return blob_name

def get_note_content(blob_name: str) -> str:
    """
    Downloads note content from GCS as string.
    """
    bucket = get_bucket()
    blob = bucket.blob(blob_name)
    return blob.download_as_text()
