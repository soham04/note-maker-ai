import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io

def get_credentials(refresh_token: str, client_id: str, client_secret: str) -> Credentials:
    return Credentials(
        None, # access_token (will be refreshed)
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/drive.file"]
    )

def create_folder_if_not_exists(service, folder_name: str) -> str:
    query = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and trashed=false"
    results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    files = results.get('files', [])
    
    if files:
        return files[0]['id']
    
    file_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder'
    }
    file = service.files().create(body=file_metadata, fields='id').execute()
    return file.get('id')

def upload_to_drive(refresh_token: str, content: str, video_title: str) -> str:
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    
    if not refresh_token or not client_id or not client_secret:
        raise ValueError("Missing credentials for Drive upload")
        
    creds = get_credentials(refresh_token, client_id, client_secret)
    service = build('drive', 'v3', credentials=creds)
    
    folder_id = create_folder_if_not_exists(service, "YouTube Notes")
    
    file_name = f"{video_title}.md"
    
    # Check if file exists to overwrite
    query = f"name = '{file_name}' and '{folder_id}' in parents and trashed = false"
    results = service.files().list(q=query, spaces='drive', fields='files(id)').execute()
    existing_files = results.get('files', [])
    
    file_metadata = {
        'name': file_name,
        'parents': [folder_id],
        'mimeType': 'text/markdown'
    }
    
    media = MediaIoBaseUpload(
        io.BytesIO(content.encode('utf-8')),
        mimetype='text/markdown',
        resumable=True
    )
    
    if existing_files:
        # Overwrite
        file_id = existing_files[0]['id']
        file = service.files().update(
            fileId=file_id,
            body=file_metadata,  # body might not be needed for just content update, but good for name assurance
            media_body=media,
            fields='id, webViewLink'
        ).execute()
    else:
        # Create new
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink'
        ).execute()
        
    return file.get('webViewLink')
