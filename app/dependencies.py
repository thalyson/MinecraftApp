"""FastAPI dependencies and utility functions.

This module contains shared dependencies such as a rate limiter for order placement.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import Depends, HTTPException, status

from .auth import get_current_user
from .models import User

ORDER_RATE_LIMIT = 10  # orders per minute
_order_timestamps: Dict[int, Deque[float]] = defaultdict(lambda: deque(maxlen=ORDER_RATE_LIMIT))


def enforce_order_rate_limit(current_user: User = Depends(get_current_user)) -> User:
    """Dependency to enforce a simple per-user order rate limit.

    If the user has placed 10 or more orders in the last 60 seconds, raises 429.
    """
    now = time.time()
    timestamps = _order_timestamps[current_user.id]
    # Remove timestamps older than 60 seconds
    while timestamps and now - timestamps[0] > 60:
        timestamps.popleft()
    if len(timestamps) >= ORDER_RATE_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many orders, please slow down.",
        )
    # Append current timestamp
    timestamps.append(now)
    return current_user