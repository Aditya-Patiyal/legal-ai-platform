from __future__ import annotations

import secrets
from typing import Any

import hashlib
import os

from .database import execute, fetch_one, row_to_dict


def hash_password(password: str) -> str:
    salt = os.urandom(32)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return salt.hex() + ':' + key.hex()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        salt_hex, key_hex = password_hash.split(':')
        salt = bytes.fromhex(salt_hex)
        stored_key = bytes.fromhex(key_hex)
        new_key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
        return secrets.compare_digest(stored_key, new_key)
    except (ValueError, AttributeError):
        return False


def create_user(name: str, email: str, password: str) -> dict[str, Any]:
    password_hash = hash_password(password)
    user_id = execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        (name.strip(), email.strip().lower(), password_hash),
    )
    user = get_user_by_id(user_id)
    if not user:
        raise ValueError("Failed to create user")
    return user


def get_user_by_email(email: str) -> dict[str, Any] | None:
    row = fetch_one("SELECT * FROM users WHERE email = ?", (email.strip().lower(),))
    return row_to_dict(row)


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    row = fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))
    return row_to_dict(row)


def authenticate_user(email: str, password: str) -> dict[str, Any] | None:
    user = get_user_by_email(email)
    if not user:
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    return user


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    execute("INSERT INTO sessions (user_id, token) VALUES (?, ?)", (user_id, token))
    return token


def get_user_by_session(token: str) -> dict[str, Any] | None:
    row = fetch_one(
        """
        SELECT users.*
        FROM sessions
        JOIN users ON users.id = sessions.user_id
        WHERE sessions.token = ?
        """,
        (token,),
    )
    return row_to_dict(row)


def delete_session(token: str) -> None:
    execute("DELETE FROM sessions WHERE token = ?", (token,))
