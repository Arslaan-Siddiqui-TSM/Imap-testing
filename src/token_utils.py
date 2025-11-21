import os
import base64
import json
import requests
from typing import Optional, Dict


# Where to write updated env vars (default: ".env" in project root)
ENV_FILE_PATH = os.getenv("ENV_FILE_PATH", ".env")


# ---------------- internal helpers ----------------


def _update_env_file(key: str, value: str, env_path: str = ENV_FILE_PATH) -> None:
    """
    Update KEY=VALUE in the .env file, or append it if missing.
    Also updates os.environ so the current process sees the new value.
    """
    if not value:
        return

    os.environ[key] = value

    try:
        lines = []
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

        found = False
        for i, line in enumerate(lines):
            # very simple KEY=... matcher; ignores comments / exports
            if line.startswith(f"{key}="):
                lines[i] = f"{key}={value}\n"
                found = True
                break

        if not found:
            lines.append(f"{key}={value}\n")

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
    except Exception as e:
        # Non-fatal: your app should still work even if we can't write the file
        print(f"Warning: failed to update {env_path} for {key}: {e}")


# ---------------- Gmail helpers ----------------


def get_gmail_email(access_token: str, timeout: int = 10) -> Optional[str]:
    """Return the Gmail address for the access_token using Gmail API /users/me/profile."""
    if not access_token:
        return None
    url = "https://www.googleapis.com/gmail/v1/users/me/profile"
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("emailAddress")
    except requests.RequestException:
        return None
    return None


def refresh_gmail_access_token(refresh_token: str, timeout: int = 10) -> Optional[str]:
    """
    Use the OAuth2 refresh_token to get a fresh Gmail access token.

    If Google returns a new refresh_token (rotation), we transparently
    update GMAIL_REFRESH_TOKEN in both os.environ and the .env file.
    """
    if not refresh_token:
        return None

    client_id = os.getenv("GMAIL_CLIENT_ID")
    client_secret = os.getenv("GMAIL_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError("GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET must be set")

    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }

    try:
        resp = requests.post(
            "https://oauth2.googleapis.com/token",
            data=data,
            timeout=timeout,
        )
        if resp.status_code == 200:
            body = resp.json()
            access_token = body.get("access_token")
            new_refresh = body.get("refresh_token")

            # Google may or may not return a new refresh token.
            if new_refresh and new_refresh != refresh_token:
                _update_env_file("GMAIL_REFRESH_TOKEN", new_refresh)

            return access_token
        else:
            print("Failed to refresh Gmail token:", resp.status_code, resp.text)
    except requests.RequestException as e:
        print("Error refreshing Gmail token:", e)

    return None


# ---------------- Outlook helpers ----------------


def get_outlook_email_from_msal_result(msal_result: Dict, timeout: int = 10) -> Optional[str]:
    """Extract an Outlook/Microsoft account email from msal acquire_token result.

    Tries id_token_claims first, then Graph /me as a fallback.
    Useful in the interactive outlook_oauth.py flow.
    """
    if not msal_result:
        return None

    # 1) Try id token claims first
    id_claims = msal_result.get("id_token_claims") or {}
    for key in ("preferred_username", "email", "upn", "unique_name", "userPrincipalName"):
        val = id_claims.get(key)
        if val:
            return val

    # 2) Try Graph /me using the access token
    access_token = msal_result.get("access_token")
    if access_token:
        url = "https://graph.microsoft.com/v1.0/me"
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("mail") or data.get("userPrincipalName")
        except requests.RequestException:
            return None

    return None


def get_outlook_email_from_access_token(access_token: str) -> Optional[str]:
    """Extract Outlook email/UPN from the access token JWT itself."""
    if not access_token:
        return None

    try:
        # JWT: header.payload.signature
        parts = access_token.split(".")
        if len(parts) < 2:
            return None

        payload_b64 = parts[1]
        # base64url decode with padding
        padding = "=" * (-len(payload_b64) % 4)
        payload_bytes = base64.urlsafe_b64decode(payload_b64 + padding)
        claims = json.loads(payload_bytes.decode("utf-8"))

        for key in ("preferred_username", "email", "upn", "unique_name", "userPrincipalName"):
            val = claims.get(key)
            if val:
                return val
    except Exception:
        return None

    return None


def refresh_outlook_access_token(refresh_token: str, timeout: int = 10) -> Optional[str]:
    """
    Use the OAuth2 refresh_token to get a fresh Outlook IMAP access token.

    If Microsoft rotates the refresh token, we update OUTLOOK_REFRESH_TOKEN
    in os.environ and the .env file.
    """
    if not refresh_token:
        return None

    client_id = os.getenv("OUTLOOK_CLIENT_ID")
    tenant_id = os.getenv("OUTLOOK_TENANT_ID", "common")

    if not client_id:
        raise RuntimeError("OUTLOOK_CLIENT_ID must be set in .env")

    data = {
        "client_id": client_id,
        "scope": "https://outlook.office.com/IMAP.AccessAsUser.All offline_access",
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }

    try:
        resp = requests.post(
            f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
            data=data,
            timeout=timeout,
        )
        if resp.status_code == 200:
            body = resp.json()
            access_token = body.get("access_token")
            new_refresh = body.get("refresh_token")

            if new_refresh and new_refresh != refresh_token:
                _update_env_file("OUTLOOK_REFRESH_TOKEN", new_refresh)

            return access_token

        print("Outlook refresh failed:", resp.status_code, resp.text)
    except requests.RequestException as e:
        print("Error refreshing Outlook token:", e)

    return None
