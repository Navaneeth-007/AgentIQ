"""Keep configured credentials out of saved tool errors and API responses."""

import os


def safe_error(error: Exception | str) -> str:
    message = str(error)
    for name, value in os.environ.items():
        if value and any(
            part in name for part in ("API_KEY", "PASSWORD", "TOKEN", "POSTGRES_URL")
        ):
            message = message.replace(value, "[redacted]")
    return message
