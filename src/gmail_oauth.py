import os
from typing import Dict

from google_auth_oauthlib.flow import InstalledAppFlow
from dotenv import load_dotenv

from src.token_utils import get_gmail_email

load_dotenv()

SCOPES = ["https://mail.google.com/"]


def _build_client_config(client_id: str, client_secret: str) -> Dict:
    """Construct a minimal client config compatible with google-auth-oauthlib.

    This mirrors the structure of a client_secrets.json but is created from
    environment variables so the JSON file is not required.
    """
    return {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            # use the loopback redirect URI used by InstalledAppFlow
            "redirect_uris": ["http://localhost"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def generate_gmail_oauth():
    client_id = os.getenv("GMAIL_CLIENT_ID")
    client_secret = os.getenv("GMAIL_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise RuntimeError(
            "GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET must be set in the environment or .env"
        )

    client_config = _build_client_config(client_id, client_secret)

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(
        port=0,
        authorization_prompt_message="Please authorize the app.",
        authorization_url_params={"access_type": "offline", "prompt": "consent"},
    )

    print("\n--- SAVE THESE INTO .env ---")
    # access token is short-lived (mainly for debugging)
    print("GMAIL_ACCESS_TOKEN=", creds.token)
    # this is the important one
    print("GMAIL_REFRESH_TOKEN=", creds.refresh_token)
    print("GMAIL_CLIENT_ID=", client_id)
    print("GMAIL_CLIENT_SECRET=", client_secret)

    # attempt to discover the Gmail email address using the access token
    if getattr(creds, "token", None):
        discovered = get_gmail_email(str(creds.token))
        if discovered:
            print("GMAIL_EMAIL=", discovered)


if __name__ == "__main__":
    generate_gmail_oauth()
