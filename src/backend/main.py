import os
import urllib.parse
import secrets
from typing import Dict

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse, HTMLResponse
from dotenv import load_dotenv

# Load env BEFORE importing anything that uses it
load_dotenv()

from src.auth import get_session, User
from src.accounts import create_email_account_for_user
from src.token_utils import get_gmail_email, get_outlook_email_from_access_token

app = FastAPI(title="IMAP Backend OAuth Service")

import logging
logging.getLogger("uvicorn.access").disabled = True

# ----------------- Common helpers -----------------

STATE_STORE: Dict[str, int] = {}  # state -> user_id (dev-only, in-memory)


def get_backend_base_url() -> str:
    return os.getenv("BACKEND_BASE_URL", "http://localhost:8000")


# ----------------- Gmail OAuth -----------------

GMAIL_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GMAIL_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"


def get_gmail_redirect_uri() -> str:
    # Backend callback URI
    return os.getenv(
        "GMAIL_REDIRECT_URI",
        get_backend_base_url() + "/oauth/google/callback",
    )


@app.get("/health", response_class=HTMLResponse)
def health() -> str:
    return "<h3>Backend is running ✅</h3>"


@app.get("/oauth/google/start")
def oauth_google_start(user_id: int = Query(..., description="App user ID")):
    """Start Gmail OAuth for the given app user."""
    client_id = os.getenv("GMAIL_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=500, detail="GMAIL_CLIENT_ID not configured")

    # validate user exists
    with get_session() as session:
        user = session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=400, detail="Unknown user_id")

    state = secrets.token_urlsafe(16)
    STATE_STORE[state] = user_id

    params = {
        "client_id": client_id,
        "redirect_uri": get_gmail_redirect_uri(),
        "response_type": "code",
        "scope": "https://mail.google.com/",
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }

    auth_url = GMAIL_AUTH_ENDPOINT + "?" + urllib.parse.urlencode(
        params, quote_via=urllib.parse.quote
    )
    return RedirectResponse(auth_url, status_code=302)


@app.get("/oauth/google/callback", response_class=HTMLResponse)
def oauth_google_callback(code: str, state: str):
    """Gmail redirects here after user consents."""
    if state not in STATE_STORE:
        raise HTTPException(status_code=400, detail="Invalid or expired state")

    user_id = STATE_STORE.pop(state)

    client_id = os.getenv("GMAIL_CLIENT_ID")
    client_secret = os.getenv("GMAIL_CLIENT_SECRET")
    redirect_uri = get_gmail_redirect_uri()

    if not client_id or not client_secret:
        raise HTTPException(status_code=500, detail="Gmail OAuth not configured")

    data = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }

    try:
        resp = requests.post(GMAIL_TOKEN_ENDPOINT, data=data, timeout=10)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Gmail token request failed: {e}")

    if resp.status_code != 200:
        raise HTTPException(
            status_code=502, detail=f"Gmail token exchange failed: {resp.text}"
        )

    body = resp.json()
    access_token = body.get("access_token")
    refresh_token = body.get("refresh_token")

    if not refresh_token:
        html = """
        <h3>Could not obtain a refresh token from Google.</h3>
        <p>
        This usually happens if you've already granted access before.
        Try removing this app's access from your Google Account security settings
        and then start the connection again.
        </p>
        """
        return HTMLResponse(content=html, status_code=200)

    email_addr = get_gmail_email(access_token or "")
    if not email_addr:
        raise HTTPException(
            status_code=502, detail="Could not determine Gmail email address from token"
        )

    try:
        create_email_account_for_user(
            user_id=user_id,
            provider="gmail",
            email_address=email_addr,
            refresh_token=refresh_token,
        )
    except Exception as e:
        html = f"""
        <h3>Account save error</h3>
        <p>Failed to save Gmail account for user {user_id}.</p>
        <pre>{e}</pre>
        """
        return HTMLResponse(content=html, status_code=200)

    html = f"""
    <h3>✅ Gmail account connected</h3>
    <p>Account: <strong>{email_addr}</strong></p>
    <p>You can now close this tab and return to the IMAP app.</p>
    """
    return HTMLResponse(content=html, status_code=200)


# ----------------- Outlook OAuth -----------------

OUTLOOK_AUTH_BASE = "https://login.microsoftonline.com"
OUTLOOK_TOKEN_PATH = "/oauth2/v2.0/token"
OUTLOOK_AUTH_PATH = "/oauth2/v2.0/authorize"


def get_outlook_tenant() -> str:
    return os.getenv("OUTLOOK_TENANT_ID", "common")


def get_outlook_redirect_uri() -> str:
    return os.getenv(
        "OUTLOOK_REDIRECT_URI",
        get_backend_base_url() + "/oauth/outlook/callback",
    )


@app.get("/oauth/outlook/start")
def oauth_outlook_start(user_id: int = Query(..., description="App user ID")):
    """Start Outlook OAuth for the given app user."""
    client_id = os.getenv("OUTLOOK_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=500, detail="OUTLOOK_CLIENT_ID not configured")

    # validate user exists
    with get_session() as session:
        user = session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=400, detail="Unknown user_id")

    tenant = get_outlook_tenant()
    auth_endpoint = f"{OUTLOOK_AUTH_BASE}/{tenant}{OUTLOOK_AUTH_PATH}"

    state = secrets.token_urlsafe(16)
    STATE_STORE[state] = user_id

    scopes = (
        "offline_access "
        "https://outlook.office.com/IMAP.AccessAsUser.All "
        "https://graph.microsoft.com/User.Read"
    )

    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": get_outlook_redirect_uri(),
        "response_mode": "query",
        "scope": scopes,
        "state": state,
    }

    auth_url = auth_endpoint + "?" + urllib.parse.urlencode(
        params, quote_via=urllib.parse.quote
    )
    return RedirectResponse(auth_url, status_code=302)


@app.get("/oauth/outlook/callback", response_class=HTMLResponse)
def oauth_outlook_callback(code: str, state: str):
    """Microsoft redirects here after user consents."""
    if state not in STATE_STORE:
        raise HTTPException(status_code=400, detail="Invalid or expired state")

    user_id = STATE_STORE.pop(state)

    client_id = os.getenv("OUTLOOK_CLIENT_ID")
    client_secret = os.getenv("OUTLOOK_CLIENT_SECRET")
    tenant = get_outlook_tenant()
    redirect_uri = get_outlook_redirect_uri()

    if not client_id or not client_secret:
        raise HTTPException(status_code=500, detail="Outlook OAuth not configured")

    token_endpoint = f"{OUTLOOK_AUTH_BASE}/{tenant}{OUTLOOK_TOKEN_PATH}"

    scopes = (
        "offline_access "
        "https://outlook.office.com/IMAP.AccessAsUser.All "
        "https://graph.microsoft.com/User.Read"
    )

    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "scope": scopes,
    }

    try:
        resp = requests.post(token_endpoint, data=data, timeout=10)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Outlook token request failed: {e}")

    if resp.status_code != 200:
        raise HTTPException(
            status_code=502, detail=f"Outlook token exchange failed: {resp.text}"
        )

    body = resp.json()
    access_token = body.get("access_token")
    refresh_token = body.get("refresh_token")

    if not refresh_token:
        html = """
        <h3>Could not obtain a refresh token from Microsoft.</h3>
        <p>
        This usually happens if you've already granted access before without requesting offline_access,
        or policies restrict issuing refresh tokens.
        Try removing this app's access from your Microsoft Account / Entra ID,
        then start the connection again.
        </p>
        """
        return HTMLResponse(content=html, status_code=200)

    email_addr = get_outlook_email_from_access_token(access_token or "")
    if not email_addr:
        raise HTTPException(
            status_code=502,
            detail="Could not determine Outlook email address from token",
        )

    try:
        create_email_account_for_user(
            user_id=user_id,
            provider="outlook",
            email_address=email_addr,
            refresh_token=refresh_token,
        )
    except Exception as e:
        html = f"""
        <h3>Account save error</h3>
        <p>Failed to save Outlook account for user {user_id}.</p>
        <pre>{e}</pre>
        """
        return HTMLResponse(content=html, status_code=200)

    html = f"""
    <h3>✅ Outlook account connected</h3>
    <p>Account: <strong>{email_addr}</strong></p>
    <p>You can now close this tab and return to the IMAP app.</p>
    """
    return HTMLResponse(content=html, status_code=200)
