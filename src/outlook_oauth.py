import os
import msal
from dotenv import load_dotenv

from src.token_utils import get_outlook_email_from_msal_result

load_dotenv()


SCOPES = ["https://outlook.office.com/IMAP.AccessAsUser.All"]


def generate_outlook_token():
    client_id = os.getenv("OUTLOOK_CLIENT_ID")
    tenant_id = os.getenv("OUTLOOK_TENANT_ID", "common")

    if not client_id:
        raise RuntimeError("OUTLOOK_CLIENT_ID must be set in environment or .env")

    # Use the base authority; MSAL will use the v2.0 endpoint for these scopes
    app = msal.PublicClientApplication(
        client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
    )

    result = app.acquire_token_interactive(
        SCOPES,
        prompt="select_account",
    )

    print("\n--- SAVE INTO .env ---")
    # Access token: short-lived, mainly for debugging
    print("OUTLOOK_ACCESS_TOKEN=", result.get("access_token"))
    # Refresh token: this is what you actually keep in .env
    print("OUTLOOK_REFRESH_TOKEN=", result.get("refresh_token"))

    # Try to discover email from the token/MSAL result
    discovered = get_outlook_email_from_msal_result(result)
    if discovered:
        print("OUTLOOK_EMAIL=", discovered)


if __name__ == "__main__":
    generate_outlook_token()
