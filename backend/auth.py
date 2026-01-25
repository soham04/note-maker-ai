import os
import secrets
from typing import Optional, Dict
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from google_auth_oauthlib.flow import Flow
from jose import jwt, JWTError
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

router = APIRouter()

# Configuration
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:8000/auth/google/callback")
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(32))
ALGORITHM = "HS256"

# Scopes required
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/drive.file"
]

# In-memory storage for simplicity (REPLACE with DB in production)
# mapping google_id -> refresh_token
user_refresh_tokens: Dict[str, str] = {}

def create_jwt_token(data: dict):
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)

def decode_jwt_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None

def get_current_user_token(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    token = auth_header.split(" ")[1]
    payload = decode_jwt_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload

@router.get("/auth/google")
async def login_google():
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Server misconfigured: Missing Google Credentials")
    
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    return RedirectResponse(authorization_url)

@router.get("/auth/google/callback")
async def auth_google_callback(code: str, state: Optional[str] = None):
    try:
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI
        )
        flow.fetch_token(code=code)
        credentials = flow.credentials
        
        # Get user info
        from googleapiclient.discovery import build
        service = build('oauth2', 'v2', credentials=credentials)
        user_info = service.userinfo().get().execute()
        
        google_id = user_info['id']
        email = user_info['email']
        
        # Store refresh token (encrypted in real app)
        if credentials.refresh_token:
            user_refresh_tokens[google_id] = credentials.refresh_token
        else:
            # If no refresh token, we might already have one or user didn't grant offline access properly
            # For this simplified flow, we warn or assume we have it if it's a re-login
            pass

        # Issue JWT
        token = create_jwt_token({"sub": google_id, "email": email})
        
    # Redirect back to extension via postMessage
        
        html_content = f"""
        <html>
            <body>
                <h1>Login Successful</h1>
                <p>You can close this window now.</p>
                <script>
                    // Send token to the opener (the extension on YouTube)
                    if (window.opener) {{
                        window.opener.postMessage({{ type: 'AUTH_SUCCESS', token: '{token}' }}, '*');
                    }}
                    // Also try to close
                    setTimeout(() => window.close(), 1000);
                </script>
            </body>
        </html>
        """
        return HTMLResponse(content=html_content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
