# src/imap_client.py

import imaplib
import asyncio
from typing import List, Optional, Any, Callable


class AsyncIMAPClient:
    """
    Fully async IMAP client using asyncio.to_thread around imaplib.IMAP4_SSL.

    - Supports Gmail + Outlook via XOAUTH2 (Bearer tokens) or password (if use_oauth=False).
    - Uses an asyncio.Lock to ensure a single connection isn't used concurrently.
    """

    GMAIL_IMAP = "imap.gmail.com"
    OUTLOOK_IMAP = "outlook.office365.com"

    def __init__(self, provider: str, email: str, credential: str, use_oauth: bool = True):
        self.provider = provider.lower()
        self.email = email
        self.credential = credential
        self.use_oauth = use_oauth
        self._imap: Optional[imaplib.IMAP4_SSL] = None
        self._lock = asyncio.Lock()

    # ---------- internal sync helpers ----------

    def _connect_sync(self) -> imaplib.IMAP4_SSL:
        if self.provider == "gmail":
            host = self.GMAIL_IMAP
        elif self.provider == "outlook":
            host = self.OUTLOOK_IMAP
        else:
            raise Exception(f"Unsupported provider: {self.provider}")

        imap = imaplib.IMAP4_SSL(host)

        if self.use_oauth:
            auth_string = self._oauth_string()
            # authenticate exists at runtime, stubs just don't declare it
            imap.authenticate("XOAUTH2", lambda _: auth_string)  # type: ignore[attr-defined]
            print(f"{self.provider.capitalize()} IMAP connected (OAuth2)")
        else:
            imap.login(self.email, self.credential)
            print(f"{self.provider.capitalize()} IMAP connected (password login)")

        imap.select("INBOX")
        self._imap = imap
        return imap

    def _oauth_string(self) -> bytes:
        # XOAUTH2 auth string with control char 0x01 separators
        return f"user={self.email}\x01auth=Bearer {self.credential}\x01\x01".encode("utf-8")

    def _fetch_latest_sync(self, limit: int) -> List[bytes]:
        if self._imap is None:
            self._connect_sync()
        assert self._imap is not None  # for type checkers
        imap = self._imap

        status, msg_ids = imap.search(None, "ALL")
        if status != "OK":
            raise Exception(f"IMAP search failed: {status}")

        ids = msg_ids[0].split()
        if not ids:
            return []

        ids = ids[-limit:]

        # Fetch all requested messages in a single FETCH command
        # Build message set as string (e.g. "1,2,3") for type compatibility
        id_list = ",".join(mid.decode() for mid in ids)
        status, msg_data = imap.fetch(id_list, "(RFC822)")
        if status != "OK":
            raise Exception(f"IMAP fetch failed: {status}")

        emails: List[bytes] = []
        if msg_data:
            for part in msg_data:
                if isinstance(part, tuple) and len(part) >= 2 and part[1] is not None:
                    emails.append(part[1])

        return emails

    def _logout_sync(self) -> None:
        if self._imap is not None:
            try:
                self._imap.logout()
            finally:
                self._imap = None

    # ---------- generic async runner ----------

    async def _run(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        return await asyncio.to_thread(func, *args, **kwargs)

    # ---------- public async API ----------

    async def connect(self) -> Any:
        async with self._lock:
            return await self._run(self._connect_sync)

    async def fetch_latest(self, limit: int = 5) -> List[bytes]:
        async with self._lock:
            return await self._run(self._fetch_latest_sync, limit)

    async def close(self) -> None:
        async with self._lock:
            await self._run(self._logout_sync)
