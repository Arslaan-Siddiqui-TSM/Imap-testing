from typing import List, Optional, Tuple

from sqlmodel import select

from src.auth import (
    get_session,
    EmailAccount,
    encrypt_token,
    decrypt_token,
)
from src.token_utils import (
    refresh_gmail_access_token,
    refresh_outlook_access_token,
)


def list_email_accounts_for_user(user_id: int) -> List[EmailAccount]:
    with get_session() as session:
        stmt = select(EmailAccount).where(EmailAccount.user_id == user_id)
        return list(session.exec(stmt))


def create_email_account_for_user(
    user_id: int,
    provider: str,
    email_address: str,
    refresh_token: str,
) -> EmailAccount:
    provider = provider.lower().strip()
    enc = encrypt_token(refresh_token)

    acc = EmailAccount(
        user_id=user_id,
        provider=provider,
        email_address=email_address.strip(),
        refresh_token_encrypted=enc,
    )

    with get_session() as session:
        session.add(acc)
        session.commit()
        session.refresh(acc)
    return acc


def get_email_account_for_user(user_id: int, account_id: int) -> Optional[EmailAccount]:
    with get_session() as session:
        stmt = select(EmailAccount).where(
            EmailAccount.user_id == user_id,
            EmailAccount.id == account_id,
        )
        return session.exec(stmt).first()


def get_access_token_for_account(
    user_id: int,
    account_id: int,
) -> Tuple[str, str, str]:
    """
    Resolve provider, email, and a fresh access token for the given account.

    Returns:
        (provider, email_address, access_token)
    """
    acc = get_email_account_for_user(user_id, account_id)
    if not acc:
        raise RuntimeError("Email account not found for current user")

    refresh_token = decrypt_token(acc.refresh_token_encrypted)

    if acc.provider == "gmail":
        access_token = refresh_gmail_access_token(refresh_token)
    elif acc.provider == "outlook":
        access_token = refresh_outlook_access_token(refresh_token)
    else:
        raise RuntimeError(f"Unsupported provider: {acc.provider}")

    if not access_token:
        raise RuntimeError("Failed to obtain access token from refresh token")

    return acc.provider, acc.email_address, access_token
