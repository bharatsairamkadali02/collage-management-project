"""
Helper functions and utilities for the College Management System.
Handles data transformation, DynamoDB Decimal conversion, and rate limiting.
"""
import math
import threading
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple, Union


def generate_id(prefix: str = "") -> str:
    """
    Generate a unique identifier, optionally prefixed.
    Uses UUID4 formatted with hex.
    """
    unique_str = uuid.uuid4().hex[:12]
    if prefix:
        return f"{prefix}_{unique_str}"
    return unique_str


def iso_now() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def format_date(dt: Optional[Union[datetime, str]] = None) -> str:
    """
    Format a datetime or string date to YYYY-MM-DD.
    Defaults to current UTC date if None provided.
    """
    if dt is None:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if isinstance(dt, str):
        # Return first 10 characters if already ISO string like YYYY-MM-DDTHH:MM:SS
        return dt[:10]
    return dt.strftime("%Y-%m-%d")


def to_decimal(val: Any) -> Any:
    """
    Convert floats and numeric strings to Decimal for DynamoDB storage.
    Recursively processes lists and dictionaries.
    """
    if isinstance(val, float):
        return Decimal(str(val))
    if isinstance(val, int):
        return Decimal(val)
    if isinstance(val, list):
        return [to_decimal(item) for item in val]
    if isinstance(val, dict):
        return {k: to_decimal(v) for k, v in val.items()}
    return val


def from_decimal(obj: Any) -> Any:
    """
    Convert DynamoDB Decimal types back to Python native int or float
    for clean JSON serialization. Recursively processes lists and dicts.
    """
    if isinstance(obj, list):
        return [from_decimal(item) for item in obj]
    elif isinstance(obj, dict):
        return {k: from_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, Decimal):
        # Return int if whole number, otherwise float
        if obj % 1 == 0:
            return int(obj)
        return float(obj)
    return obj


def clean_none_values(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively remove keys with None values from a dictionary.
    DynamoDB does not accept None/null values gracefully in attribute updates.
    """
    cleaned: Dict[str, Any] = {}
    for key, value in data.items():
        if value is None:
            continue
        if isinstance(value, dict):
            cleaned[key] = clean_none_values(value)
        elif isinstance(value, list):
            cleaned[key] = [
                clean_none_values(v) if isinstance(v, dict) else v
                for v in value
                if v is not None
            ]
        else:
            cleaned[key] = value
    return cleaned


def paginate(items: List[Any], page: int = 1, page_size: int = 20) -> Dict[str, Any]:
    """
    Paginate a list of items and return metadata.
    """
    if page < 1:
        page = 1
    if page_size < 1:
        page = 20

    total_items = len(items)
    total_pages = math.ceil(total_items / page_size) if total_items > 0 else 1

    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_items = items[start_idx:end_idx]

    return {
        "items": from_decimal(page_items),
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_items": total_items,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        },
    }


class RateLimiter:
    """
    Thread-safe sliding-window rate limiter per client key (e.g. IP address).
    """
    def __init__(self, max_requests: int = 5, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.records: Dict[str, List[float]] = {}
        self.lock = threading.Lock()

    def is_allowed(self, key: str) -> Tuple[bool, int]:
        """
        Check if request is allowed for given key.
        Returns (is_allowed, remaining_attempts).
        """
        now = time.time()
        cutoff = now - self.window_seconds

        with self.lock:
            timestamps = self.records.get(key, [])
            # Filter out timestamps older than the sliding window
            timestamps = [ts for ts in timestamps if ts > cutoff]

            if len(timestamps) >= self.max_requests:
                self.records[key] = timestamps
                return False, 0

            timestamps.append(now)
            self.records[key] = timestamps
            remaining = self.max_requests - len(timestamps)
            return True, remaining

    def reset(self, key: str) -> None:
        """Reset rate limit history for a specific key."""
        with self.lock:
            if key in self.records:
                del self.records[key]
