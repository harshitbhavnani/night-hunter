from __future__ import annotations

from typing import Sequence

from src.providers.base import BaseMarketDataProvider, ProviderMessageHandler


def watch_shortlist(
    provider: BaseMarketDataProvider,
    symbols: Sequence[str],
    on_message: ProviderMessageHandler,
) -> None:
    """Start live Stage 2 monitoring for shortlisted symbols only."""

    provider.stream_bars(symbols, on_message)

