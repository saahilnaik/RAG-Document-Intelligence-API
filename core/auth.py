import hmac
from typing import Optional

from fastapi import Header, HTTPException, status

from core.config import get_settings

ANONYMOUS_USER = "anonymous"


def get_current_user(x_api_key: Optional[str] = Header(default=None)) -> str:
    """Resolve the caller's user id from the `X-API-Key` header.

    The returned id is the tenant key: documents, sessions and vector chunks
    are all scoped to it.
    """
    settings = get_settings()
    if not settings.AUTH_ENABLED:
        return ANONYMOUS_USER

    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Constant-time comparison against every configured key.
    matched: Optional[str] = None
    for key, user_id in settings.API_KEYS.items():
        if hmac.compare_digest(key.encode(), x_api_key.encode()):
            matched = user_id
    if matched is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return matched
