from __future__ import annotations

from datetime import datetime, timedelta, timezone


def utc_window(minutes: int = 90) -> tuple[datetime, datetime]:
    end = datetime.now(timezone.utc)
    return end - timedelta(minutes=minutes), end

