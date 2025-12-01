import os
from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel, Field, Session, create_engine, select
from passlib.context import CryptContext
from cryptography.fernet import Fernet, InvalidToken

# -------------------------------------------------------------------
# DB setup
# -------------------------------------------------------------------

# Use absolute path to ensure both Streamlit and FastAPI use the same database
# Find project root (where this file's parent's parent is)
_current_file = os.path.abspath(__file__)
_project_root = os.path.dirname(os.path.dirname(_current_file))
_default_db_path = os.path.join(_project_root, "app.db")

DATABASE_URL = os.getenv("APP_DB_URL", f"sqlite:///{_default_db_path}")
engine = create_engine(DATABASE_URL, echo=False)

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# -------------------------------------------------------------------
# Encryption setup (for refresh tokens)
# -------------------------------------------------------------------

FERNET_KEY = os.getenv("TOKEN_ENCRYPTION_KEY")

if FERNET_KEY:
    # Expecting a base64-encoded key
    _fernet = Fernet(FERNET_KEY.encode("utf-8"))
else:
    # Ephemeral key: tokens will not be decryptable across restarts
    _fernet = Fernet(Fernet.generate_key())
    print(
        "[WARN] TOKEN_ENCRYPTION_KEY is not set. "
        "Refresh tokens will be encrypted with an in-memory key only "
        "and will NOT be usable after a restart."
    )


def encrypt_token(raw: str) -> str:
    return _fernet.encrypt(raw.encode("utf-8")).decode("utf-8")


def decrypt_token(enc: str) -> str:
    try:
        return _fernet.decrypt(enc.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        raise ValueError("Failed to decrypt stored token; check TOKEN_ENCRYPTION_KEY.")


# -------------------------------------------------------------------
# Models
# -------------------------------------------------------------------

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    password_hash: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class EmailAccount(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    provider: str = Field(index=True)  # "gmail" or "outlook"
    email_address: str
    refresh_token_encrypted: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)


# -------------------------------------------------------------------
# Password helpers
# -------------------------------------------------------------------

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


# -------------------------------------------------------------------
# User operations
# -------------------------------------------------------------------

def get_user_by_email(email: str) -> Optional[User]:
    with get_session() as session:
        stmt = select(User).where(User.email == email.lower())
        return session.exec(stmt).first()


def register_user(email: str, password: str) -> User:
    email = email.lower().strip()
    if not email or not password:
        raise ValueError("Email and password are required")

    existing = get_user_by_email(email)
    if existing:
        raise ValueError("A user with this email already exists")

    user = User(
        email=email,
        password_hash=hash_password(password),
    )
    with get_session() as session:
        session.add(user)
        session.commit()
        session.refresh(user)
    return user


def authenticate_user(email: str, password: str) -> Optional[User]:
    email = email.lower().strip()
    user = get_user_by_email(email)
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user
