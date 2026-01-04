import os, secrets
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer(auto_error=False)

API_TOKEN = os.getenv("MBR_API_TOKEN")
if not API_TOKEN:
    raise RuntimeError("MBR_API_TOKEN is not set")

def require_token(creds: HTTPAuthorizationCredentials = Depends(bearer)) -> None:
    if not creds or creds.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    if not API_TOKEN or not secrets.compare_digest(creds.credentials, API_TOKEN):
        raise HTTPException(status_code=403, detail="Invalid token")
