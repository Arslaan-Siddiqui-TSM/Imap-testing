import asyncio
import time
import mimetypes
import os
import html

import streamlit as st
from dotenv import load_dotenv

from src.imap_client import AsyncIMAPClient
from src.email_parser import EmailParser
from src.token_utils import (
    get_gmail_email,
    refresh_gmail_access_token,
    refresh_outlook_access_token,
    get_outlook_email_from_access_token,
)

load_dotenv()

# -------------------------------------------------------------------
# Page config & light styling
# -------------------------------------------------------------------
st.set_page_config(page_title="IMAP Email Viewer POC", layout="wide")

st.markdown(
    """
    <style>
    .subject-line {
        font-weight: 600;
        font-size: 1.05rem;
    }
    .email-meta {
        font-size: 0.9rem;
        color: #666666;
    }
    .stTabs [role="tablist"] {
        border-bottom: 1px solid #e0e0e0;
    }
    .stTabs [role="tab"] {
        padding-top: 0.5rem;
        padding-bottom: 0.5rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("📬 IMAP Email Viewer")

st.caption(
    "Connect to Gmail or Outlook using OAuth2, fetch the latest emails, and inspect them in a clean viewer."
)

# -------------------------------------------------------------------
# Session state
# -------------------------------------------------------------------
if "connected" not in st.session_state:
    st.session_state.connected = False
if "parsed_messages" not in st.session_state:
    st.session_state.parsed_messages = []
if "selected_index" not in st.session_state:
    st.session_state.selected_index = 0
if "connection_info" not in st.session_state:
    st.session_state.connection_info = {}

# -------------------------------------------------------------------
# Sidebar: Connection Settings
# -------------------------------------------------------------------
with st.sidebar:
    st.header("Connection Settings")

    provider = st.selectbox("Provider", ["gmail", "outlook"])
    use_env = st.checkbox("Use credentials from .env (recommended)", value=True)

    st.markdown("### Credentials")

    manual_email: str | None = None
    manual_credential: str | None = None

    if use_env:
        if provider == "gmail":
            st.write("Using **GMAIL_REFRESH_TOKEN** / **GMAIL_ACCESS_TOKEN** from `.env`.")
            st.write("Email will be auto-detected from token if `GMAIL_EMAIL` is missing.")
        else:
            st.write("Using **OUTLOOK_REFRESH_TOKEN** / **OUTLOOK_ACCESS_TOKEN** from `.env`.")
            st.write("Email will be auto-detected from token if `OUTLOOK_EMAIL` is missing.")
    else:
        manual_email = st.text_input("Email address")
        manual_credential = st.text_input(
            "Credential (access token / app password)",
            type="password",
        )

    use_oauth = st.checkbox("Use OAuth (XOAUTH2)", value=True)
    fetch_limit = st.slider("Fetch latest N emails", min_value=1, max_value=50, value=10)

    st.markdown("---")
    connect_btn = st.button("🔌 Connect & Fetch")

# -------------------------------------------------------------------
# Connect + Fetch (Async)
# -------------------------------------------------------------------
async def _async_connect_and_fetch(
    provider: str,
    use_env: bool,
    manual_email: str | None,
    manual_credential: str | None,
    use_oauth: bool,
    limit: int,
):
    start = time.time()

    provider = provider.lower()
    email_addr: str | None = None
    access_token: str | None = None

    # ----- Gmail -----
    if provider == "gmail":
        if use_env:
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
                    "No Gmail token found. Set GMAIL_REFRESH_TOKEN or GMAIL_ACCESS_TOKEN in .env."
                )

            email_addr = os.getenv("GMAIL_EMAIL") or get_gmail_email(gmail_token)
            if not email_addr:
                raise RuntimeError(
                    "Could not determine Gmail email address. "
                    "Set GMAIL_EMAIL or ensure the token can call Gmail API."
                )

            access_token = gmail_token
        else:
            if not manual_email or not manual_credential:
                raise RuntimeError("Email and credential are required for manual Gmail connection.")
            email_addr = manual_email
            access_token = manual_credential

        client = AsyncIMAPClient(
            provider="gmail",
            email=email_addr,
            credential=access_token,
            use_oauth=use_oauth,
        )

    # ----- Outlook -----
    else:
        if use_env:
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
                    "No Outlook token found. "
                    "Set OUTLOOK_REFRESH_TOKEN or OUTLOOK_ACCESS_TOKEN in .env."
                )

            email_addr = (
                get_outlook_email_from_access_token(outlook_token)
                or os.getenv("OUTLOOK_EMAIL")
            )
            if not email_addr:
                raise RuntimeError(
                    "Could not determine Outlook email address. "
                    "Set OUTLOOK_EMAIL or ensure the token has email/UPN claims."
                )

            access_token = outlook_token
        else:
            if not manual_email or not manual_credential:
                raise RuntimeError("Email and credential are required for manual Outlook connection.")
            email_addr = manual_email
            access_token = manual_credential

        client = AsyncIMAPClient(
            provider="outlook",
            email=email_addr,
            credential=access_token,
            use_oauth=use_oauth,
        )

    # Connect + fetch
    await client.connect()
    raw_list = await client.fetch_latest(limit)
    await client.close()

    parsed = [EmailParser.parse(raw) for raw in raw_list]

    end = time.time()
    total_time = round(end - start, 2)

    st.session_state.parsed_messages = parsed
    st.session_state.connected = True
    st.session_state.selected_index = 0
    st.session_state.connection_info = {
        "provider": provider,
        "email": email_addr,
        "count": len(parsed),
        "time": total_time,
    }


def connect_and_fetch(provider, use_env, manual_email, manual_credential, use_oauth, limit):
    try:
        asyncio.run(
            _async_connect_and_fetch(
                provider,
                use_env,
                manual_email,
                manual_credential,
                use_oauth,
                limit,
            )
        )
        info = st.session_state.connection_info
        st.success(
            f"Connected to **{info['provider']}** as **{info['email']}** — "
            f"fetched {info['count']} emails in {info['time']} seconds."
        )
    except Exception as e:
        st.session_state.connected = False
        st.session_state.parsed_messages = []
        st.error(f"Connection or fetch failed: {e}")


if connect_btn:
    connect_and_fetch(provider, use_env, manual_email, manual_credential, use_oauth, fetch_limit)

# -------------------------------------------------------------------
# Main Layout: Email List + Tabs Viewer
# -------------------------------------------------------------------
if not st.session_state.connected:
    st.info("Use the sidebar to connect and fetch emails.")
else:
    parsed = st.session_state.parsed_messages
    info = st.session_state.connection_info

    # Connection summary pill
    with st.container():
        st.markdown(
            f"""
            <div style="
                padding: 0.45rem 0.9rem;
                border-radius: 999px;
                background-color: var(--secondary-background-color);
                color: var(--text-color);
                display: inline-block;
                margin-bottom: 0.75rem;
                font-size: 0.9rem;
                box-shadow: 0 0 0 1px rgba(255,255,255,0.08), 0 2px 6px rgba(0,0,0,0.25);
            ">
                <strong>{info.get('provider','').upper()}</strong> • 
                {info.get('email','')} • 
                {info.get('count',0)} messages
            </div>
            """,
            unsafe_allow_html=True,
        )



    col_list, col_view = st.columns([1, 2])

    # -------- Email list (left) --------
    with col_list:
        st.subheader("Inbox")

        display_items = []
        for i, m in enumerate(parsed):
            subj = m["subject"] or "(no subject)"
            frm = m["from"] or "(unknown sender)"
            display_items.append(f"{i+1}. {subj} — {frm}")

        selected_label = st.selectbox("Select message", options=display_items)
        selected_index = display_items.index(selected_label)
        st.session_state.selected_index = selected_index
        msg = parsed[selected_index]

    # -------- Email viewer (right) with tabs --------
    with col_view:
        preview_start = time.time()

        subject = msg.get("subject") or "(no subject)"
        sender = msg.get("from") or "(unknown sender)"
        to = msg.get("to") or ""
        date = msg.get("date") or ""

        # Escape to avoid invalid HTML tags from things like <email@domain>
        subject_html = html.escape(subject)
        sender_html = html.escape(sender)
        to_html = html.escape(to)
        date_html = html.escape(date)

        st.markdown(
            f"<div class='subject-line'>{subject_html}</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<div class='email-meta'>From: {sender_html}<br>To: {to_html}<br>Date: {date_html}</div>",
            unsafe_allow_html=True,
        )


        tabs = st.tabs(["Overview", "Plain Text", "HTML", "Attachments", "Raw JSON"])

        # Overview tab
        with tabs[0]:
            st.markdown("#### Summary")
            st.write(
                {
                    "Subject": msg["subject"],
                    "From": msg["from"],
                    "To": msg["to"],
                    "Date": msg["date"],
                    "Attachments": len(msg["attachments"]),
                }
            )

        # Plain text
        with tabs[1]:
            st.markdown("#### Plain Text Body")
            st.code(msg.get("text", "")[:8000] or "(no plain text)")

        # HTML
        with tabs[2]:
            st.markdown("#### HTML Body")
            if msg.get("html"):
                st.markdown(msg["html"], unsafe_allow_html=True)
            else:
                st.info("No HTML body found.")

        # Attachments
        with tabs[3]:
            st.markdown("#### Attachments")
            if msg.get("attachments"):
                for attachment in msg["attachments"]:
                    fn = attachment.get("filename") or "attachment"
                    size = attachment.get("size_kb", 0)
                    content = attachment.get("content", b"")

                    mime_type, _ = mimetypes.guess_type(fn)
                    mime_type = mime_type or "application/octet-stream"

                    st.write(f"📎 **{fn}** — {size} KB")
                    st.download_button(
                        label=f"Download {fn}",
                        data=content,
                        file_name=fn,
                        mime=mime_type,
                    )

                    # Simple preview by type
                    if mime_type.startswith("image/"):
                        st.image(content, caption=fn, use_column_width=True)
                    elif mime_type == "application/pdf":
                        import base64

                        base64_pdf = base64.b64encode(content).decode("utf-8")
                        st.markdown(
                            f"""
                            <iframe src="data:application/pdf;base64,{base64_pdf}"
                            width="100%" height="500px"></iframe>
                            """,
                            unsafe_allow_html=True,
                        )
                    elif mime_type.startswith("text/"):
                        st.code(content.decode("utf-8", errors="ignore"))
                    elif mime_type == "text/html":
                        st.markdown(
                            content.decode("utf-8", errors="ignore"),
                            unsafe_allow_html=True,
                        )
                    else:
                        st.info("Preview not available — download to view.")
            else:
                st.info("No attachments found.")

        # Raw JSON
        with tabs[4]:
            st.markdown("#### Raw Parsed JSON")
            st.json(msg)

        preview_time = round(time.time() - preview_start, 3)
        st.caption(f"⏱ Email rendered in {preview_time} seconds")

# -------------------------------------------------------------------
# Footer
# -------------------------------------------------------------------
st.markdown("---")
st.caption("IMAP Viewer — Gmail & Outlook")
