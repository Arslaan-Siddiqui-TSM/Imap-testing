# test_run.py

import os
import asyncio
from dotenv import load_dotenv

from src.email_parser import EmailParser
from src.imap_client import AsyncIMAPClient
from src.token_utils import (
    get_gmail_email,
    refresh_gmail_access_token,
    refresh_outlook_access_token,
    get_outlook_email_from_access_token,
)

load_dotenv()


def show(parsed):
    print("\n=========================")
    print("Subject:", parsed["subject"])
    print("From:", parsed["from"])
    print("To:", parsed["to"])
    print("Text:", parsed["text"][:200], "...")
    print("HTML:", parsed["html"][:200], "...")
    print("Attachments:", len(parsed["attachments"]))


async def main():
    # ----------- GMAIL -----------
    print("\n--- GMAIL IMAP (async) ---")

    gmail_token: str | None = None

    gmail_refresh = os.getenv("GMAIL_REFRESH_TOKEN")
    if gmail_refresh:
        gmail_token = refresh_gmail_access_token(gmail_refresh)

    if not gmail_token:
        gmail_access = os.getenv("GMAIL_ACCESS_TOKEN")
        if gmail_access:
            gmail_token = gmail_access

    if not gmail_token:
        raise RuntimeError(
            "Could not obtain a Gmail access token. "
            "Set GMAIL_REFRESH_TOKEN (and GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET) in .env."
        )

    gmail_email = os.getenv("GMAIL_EMAIL")
    if not gmail_email:
        gmail_email = get_gmail_email(gmail_token)

    if not gmail_email:
        raise RuntimeError(
            "Could not determine Gmail email address. "
            "Set GMAIL_EMAIL or check the token/refresh flow."
        )

    gmail_client = AsyncIMAPClient(
        provider="gmail",
        email=gmail_email,
        credential=gmail_token,
        use_oauth=True,
    )

    # ----------- OUTLOOK -----------
    print("\n--- OUTLOOK IMAP (async) ---")

    outlook_token: str | None = None

    outlook_refresh = os.getenv("OUTLOOK_REFRESH_TOKEN")
    if outlook_refresh:
        outlook_token = refresh_outlook_access_token(outlook_refresh)

    if not outlook_token:
        outlook_access = os.getenv("OUTLOOK_ACCESS_TOKEN")
        if outlook_access:
            outlook_token = outlook_access

    if not outlook_token:
        raise RuntimeError(
            "Could not obtain an Outlook access token. "
            "Set OUTLOOK_REFRESH_TOKEN (and OUTLOOK_CLIENT_ID / OUTLOOK_TENANT_ID) or OUTLOOK_ACCESS_TOKEN in .env."
        )

    outlook_email = get_outlook_email_from_access_token(outlook_token) or os.getenv("OUTLOOK_EMAIL")

    if not outlook_email:
        raise RuntimeError(
            "Could not determine Outlook email address. "
            "Ensure the token includes a username/email claim or set OUTLOOK_EMAIL in .env."
        )

    outlook_client = AsyncIMAPClient(
        provider="outlook",
        email=outlook_email,
        credential=outlook_token,
        use_oauth=True,
    )

    # ----------- connect in parallel -----------
    await asyncio.gather(
        gmail_client.connect(),
        outlook_client.connect(),
    )

    # ----------- fetch in parallel -----------
    gmail_msgs, outlook_msgs = await asyncio.gather(
        gmail_client.fetch_latest(2),
        outlook_client.fetch_latest(2),
    )

    print("\n--- GMAIL ---")
    for raw in gmail_msgs:
        show(EmailParser.parse(raw))

    print("\n--- OUTLOOK ---")
    for raw in outlook_msgs:
        show(EmailParser.parse(raw))

    await asyncio.gather(
        gmail_client.close(),
        outlook_client.close(),
    )


if __name__ == "__main__":
    asyncio.run(main())
