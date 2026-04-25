from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Mapping
from zoneinfo import ZoneInfo

from src.providers.base import BaseMarketDataProvider


MARKET_TZ = ZoneInfo("America/New_York")


def utc_window(minutes: int = 90) -> tuple[datetime, datetime]:
    end = datetime.now(timezone.utc)
    return end - timedelta(minutes=minutes), end


def last_completed_session_window(
    provider: BaseMarketDataProvider,
    minutes: int = 90,
    now: datetime | None = None,
) -> dict[str, object]:
    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    calendar_start = now_utc - timedelta(days=14)
    calendar = provider.get_market_calendar(calendar_start, now_utc)
    sessions = [_session_times(row) for row in calendar]
    completed = [session for session in sessions if session and session["close"] <= now_utc]
    if not completed:
        start, end = utc_window(minutes)
        return {
            "start": start,
            "end": end,
            "label": "Live 90-minute window",
            "mode": "live_fallback",
        }

    session = max(completed, key=lambda item: item["close"])
    start = max(session["open"], session["close"] - timedelta(minutes=minutes))
    end = session["close"]
    label = _session_label(start, end)
    return {
        "start": start,
        "end": end,
        "label": label,
        "mode": "last_session",
    }


def _session_times(row: Mapping[str, object]) -> dict[str, datetime] | None:
    date_value = row.get("date")
    open_value = row.get("open") or row.get("session_open")
    close_value = row.get("close") or row.get("session_close")
    if not date_value or not open_value or not close_value:
        return None
    open_dt = _parse_calendar_dt(str(date_value), str(open_value))
    close_dt = _parse_calendar_dt(str(date_value), str(close_value))
    if not open_dt or not close_dt:
        return None
    return {"open": open_dt, "close": close_dt}


def _parse_calendar_dt(date_value: str, time_value: str) -> datetime | None:
    normalized = time_value.replace("Z", "+00:00")
    try:
        if "T" in normalized:
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=MARKET_TZ)
            return parsed.astimezone(timezone.utc)
        parsed = datetime.fromisoformat(f"{date_value}T{normalized}")
    except ValueError:
        return None
    return parsed.replace(tzinfo=MARKET_TZ).astimezone(timezone.utc)


def _session_label(start: datetime, end: datetime) -> str:
    start_et = start.astimezone(MARKET_TZ)
    end_et = end.astimezone(MARKET_TZ)
    return f"Last regular session: {end_et:%Y-%m-%d} {start_et:%H:%M}-{end_et:%H:%M} ET"
