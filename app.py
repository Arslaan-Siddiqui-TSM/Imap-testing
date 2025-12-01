import asyncio
import time
import mimetypes
import os
import html

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from src.imap_client import AsyncIMAPClient
from src.email_parser import EmailParser
from src.token_utils import (
    get_gmail_email,
    refresh_gmail_access_token,
    refresh_outlook_access_token,
    get_outlook_email_from_access_token,
)
from src.auth import authenticate_user, register_user
from src.accounts import (
    list_email_accounts_for_user,
    create_email_account_for_user,
    get_access_token_for_account,
)


# -------------------------------------------------------------------
# Page config & styling
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
        color: #888888;
    }
    .stTabs [role="tablist"] {
        border-bottom: 1px solid #33333333;
    }
    .stTabs [role="tab"] {
        padding-top: 0.5rem;
        padding-bottom: 0.5rem;
    }
    .connect-btns {
        display: flex;
        gap: 0.5rem;
    }
    .connect-btn {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.55rem 0.9rem;
        border-radius: 8px;
        font-weight: 600;
        text-decoration: none;
        color: var(--text-color);
        background: linear-gradient(180deg, #ffffff11 0%, #ffffff06 100%);
        border: 1px solid rgba(255,255,255,0.06);
        box-shadow: 0 4px 10px rgba(0,0,0,0.18);
    }
    .connect-btn:hover { transform: translateY(-1px); }
    .connect-gmail { background: linear-gradient(90deg, #e94235 0%, #c92b1f 100%); color: white; }
    .connect-outlook { background: linear-gradient(90deg, #0078d4 0%, #005ea6 100%); color: white; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("📬 IMAP Email Viewer")

st.caption(
    "Connect multiple Gmail/Outlook accounts per user using OAuth2 refresh tokens, "
    "and inspect the latest emails in a clean viewer."
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
if "user_id" not in st.session_state:
    st.session_state.user_id = None
if "user_email" not in st.session_state:
    st.session_state.user_email = None
if "selected_account_id" not in st.session_state:
    st.session_state.selected_account_id = None

connect_btn: bool = False
fetch_limit: int = 10
# -------------------------------------------------------------------
# Sidebar: Account + Email Accounts + Connection Settings
# -------------------------------------------------------------------
with st.sidebar:
    st.header("Account")

    if st.session_state.user_id is None:
        # Tabs: Login / Register
        auth_tab = st.tabs(["Login", "Register"])

        # --- Login tab ---
        with auth_tab[0]:
            st.subheader("Login")

            login_email = st.text_input("Email", key="login_email")
            login_password = st.text_input("Password", type="password", key="login_password")
            login_btn = st.button("Sign in")

            if login_btn:
                try:
                    user = authenticate_user(login_email, login_password)
                    if user:
                        st.session_state.user_id = user.id
                        st.session_state.user_email = user.email
                        st.success(f"Logged in as {user.email}")
                        st.rerun()
                    else:
                        st.error("Invalid email or password.")
                except Exception as e:
                    st.error(f"Login failed: {e}")

        # --- Register tab ---
        with auth_tab[1]:
            st.subheader("Register")

            reg_email = st.text_input("Email ", key="reg_email")
            reg_password = st.text_input("Password ", type="password", key="reg_password")
            reg_password2 = st.text_input("Confirm Password", type="password", key="reg_password2")
            reg_btn = st.button("Create account")

            if reg_btn:
                if not reg_email or not reg_password:
                    st.error("Email and password are required.")
                elif reg_password != reg_password2:
                    st.error("Passwords do not match.")
                else:
                    try:
                        user = register_user(reg_email, reg_password)
                        st.success("Account created. You can now log in.")
                    except Exception as e:
                        st.error(f"Registration failed: {e}")
    else:
        st.subheader("Logged in")
        st.write(st.session_state.user_email)
        if st.button("Log out"):
            st.session_state.user_id = None
            st.session_state.user_email = None
            st.session_state.connected = False
            st.session_state.parsed_messages = []
            st.rerun()

        # ---------------- Email accounts for this user ----------------
        st.markdown("---")
        st.subheader("Email Accounts")

        accounts = list_email_accounts_for_user(st.session_state.user_id)
        selected_account_id = None

        if accounts:
            labels = [
                f"{acc.provider.upper()} • {acc.email_address}"
                for acc in accounts
            ]
            id_map = {labels[i]: accounts[i].id for i in range(len(accounts))}
            selected_label = st.selectbox("Select account", options=labels)
            selected_account_id = id_map[selected_label]
        else:
            st.info("No email accounts yet. Connect one below.")
            selected_account_id = None

        st.session_state.selected_account_id = selected_account_id

        # --- Connect via backend ---
        backend_base = os.getenv("BACKEND_BASE_URL", "http://localhost:8000")
        connect_gmail_url = f"{backend_base}/oauth/google/start?user_id={st.session_state.user_id}"
        connect_outlook_url = f"{backend_base}/oauth/outlook/start?user_id={st.session_state.user_id}"

        st.markdown("#### Connect new account")

        col_g, col_o = st.columns(2)

        with col_g:
            st.link_button("🔗 Connect Gmail", connect_gmail_url)

        with col_o:
            st.link_button("🔗 Connect Outlook", connect_outlook_url)

        st.caption(
            "Each button opens a new tab for provider sign-in. After you allow access, "
            "return here and the account will appear in the list above."
        )


        # Optional: advanced manual path for debug
        with st.expander("Advanced: Add with refresh token"):
            new_provider = st.selectbox("Provider", ["gmail", "outlook"], key="new_acc_provider")
            new_email = st.text_input("Email address", key="new_acc_email")
            new_refresh = st.text_area(
                "Refresh token",
                key="new_acc_refresh",
                height=100,
                help="Paste the refresh token obtained from a manual OAuth flow.",
            )
            save_btn = st.button("Save account", key="save_new_account")

            if save_btn:
                if not new_email or not new_refresh:
                    st.error("Email and refresh token are required.")
                else:
                    try:
                        create_email_account_for_user(
                            st.session_state.user_id,
                            new_provider,
                            new_email,
                            new_refresh,
                        )
                        st.success("Account added.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to add account: {e}")

        # ---------------- Connection Settings ----------------
        st.markdown("---")
        st.header("Connection Settings")

        fetch_limit = st.slider(
            "Fetch latest N emails",
            min_value=1,
            max_value=50,
            value=10,
        )

        connect_btn = st.button(
            "🔌 Connect & Fetch",
            disabled=(st.session_state.selected_account_id is None),
        )

# -------------------------------------------------------------------
# Require login
# -------------------------------------------------------------------
if st.session_state.user_id is None:
    st.info("Please log in or register using the sidebar to start using the IMAP viewer.")
    st.stop()

# -------------------------------------------------------------------
# Connect + Fetch (Async) for selected account
# -------------------------------------------------------------------
async def _async_connect_and_fetch_account(
    account_id: int,
    limit: int,
):
    start = time.time()

    user_id = st.session_state.user_id
    provider, email_addr, access_token = get_access_token_for_account(user_id, account_id)

    client = AsyncIMAPClient(
        provider=provider,
        email=email_addr,
        credential=access_token,
        use_oauth=True,
    )

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


def connect_and_fetch_selected_account(limit: int):
    account_id = st.session_state.selected_account_id
    if account_id is None:
        st.error("No account selected.")
        return

    try:
        asyncio.run(
            _async_connect_and_fetch_account(
                account_id,
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


if st.session_state.user_id is not None and "connect_btn" in locals():
    if connect_btn and st.session_state.selected_account_id is not None:
        connect_and_fetch_selected_account(fetch_limit)

# -------------------------------------------------------------------
# Main Layout: Email List + Tabs Viewer
# -------------------------------------------------------------------
if not st.session_state.connected:
    st.info("Use the sidebar to select an account and fetch emails.")
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
st.caption("IMAP Viewer — Async IMAP + Multi-Account OAuth (Gmail & Outlook)")
