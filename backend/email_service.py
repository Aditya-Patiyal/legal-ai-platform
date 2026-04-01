from __future__ import annotations


def send_email(*args: object, **kwargs: object) -> dict[str, str]:
    return {
        "status": "deferred",
        "message": "SMTP email integration is intentionally deferred in the MVP build.",
    }
