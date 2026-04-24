from __future__ import annotations

from src.providers.base import BaseMarketDataProvider
from src.storage.repositories import save_universe_snapshot
from src.universe.build_universe import build_universe


def refresh_universe(provider: BaseMarketDataProvider | None = None) -> list[dict[str, object]]:
    rows = build_universe(provider=provider)
    save_universe_snapshot(rows)
    return rows
