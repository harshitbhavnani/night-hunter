from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping, Sequence

from src.providers.base import BaseMarketDataProvider, ProviderMessageHandler
from src.utils.timeframes import last_completed_session_window


class CalendarProvider(BaseMarketDataProvider):
    def __init__(self, calendar: list[Mapping[str, object]]) -> None:
        self.calendar = calendar

    def get_assets(self):
        return []

    def get_historical_bars(self, symbols: Sequence[str], timeframe: str, start: datetime, end: datetime):
        return {}

    def get_latest_bars(self, symbols: Sequence[str]):
        return {}

    def get_market_calendar(self, start: datetime, end: datetime):
        return self.calendar

    def get_snapshots(self, symbols: Sequence[str]):
        return {}

    def stream_bars(self, symbols: Sequence[str], on_message: ProviderMessageHandler) -> None:
        raise NotImplementedError

    def stream_trades(self, symbols: Sequence[str], on_message: ProviderMessageHandler) -> None:
        raise NotImplementedError

    def stream_quotes(self, symbols: Sequence[str], on_message: ProviderMessageHandler) -> None:
        raise NotImplementedError

    def get_historical_news(self, symbols: Sequence[str], start: datetime, end: datetime):
        return {}

    def stream_news(self, symbols: Sequence[str], on_message: ProviderMessageHandler) -> None:
        raise NotImplementedError


def test_friday_night_uses_friday_close_window() -> None:
    provider = CalendarProvider([{"date": "2026-04-24", "open": "09:30", "close": "16:00"}])

    window = last_completed_session_window(provider, now=datetime(2026, 4, 25, 3, 56, tzinfo=timezone.utc))

    assert window["mode"] == "last_session"
    assert window["start"] == datetime(2026, 4, 24, 18, 30, tzinfo=timezone.utc)
    assert window["end"] == datetime(2026, 4, 24, 20, 0, tzinfo=timezone.utc)
    assert window["label"] == "Last regular session: 2026-04-24 14:30-16:00 ET"


def test_weekend_uses_previous_completed_session() -> None:
    provider = CalendarProvider(
        [
            {"date": "2026-04-23", "open": "09:30", "close": "16:00"},
            {"date": "2026-04-24", "open": "09:30", "close": "16:00"},
        ]
    )

    window = last_completed_session_window(provider, now=datetime(2026, 4, 26, 18, 0, tzinfo=timezone.utc))

    assert window["start"] == datetime(2026, 4, 24, 18, 30, tzinfo=timezone.utc)
    assert window["end"] == datetime(2026, 4, 24, 20, 0, tzinfo=timezone.utc)


def test_early_close_uses_calendar_close_time() -> None:
    provider = CalendarProvider([{"date": "2026-11-27", "open": "09:30", "close": "13:00"}])

    window = last_completed_session_window(provider, now=datetime(2026, 11, 27, 22, 0, tzinfo=timezone.utc))

    assert window["start"] == datetime(2026, 11, 27, 16, 30, tzinfo=timezone.utc)
    assert window["end"] == datetime(2026, 11, 27, 18, 0, tzinfo=timezone.utc)
    assert window["label"] == "Last regular session: 2026-11-27 11:30-13:00 ET"
