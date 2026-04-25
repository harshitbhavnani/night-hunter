from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Callable, Dict, Iterable, List, Mapping, Sequence


Bar = Mapping[str, object]
ProviderMessageHandler = Callable[[Mapping[str, object]], None]


class BaseMarketDataProvider(ABC):
    """Provider contract used by the scanner and future paid-feed adapters."""

    @abstractmethod
    def get_assets(self) -> List[Mapping[str, object]]:
        raise NotImplementedError

    @abstractmethod
    def get_historical_bars(
        self,
        symbols: Sequence[str],
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> Dict[str, List[Bar]]:
        raise NotImplementedError

    @abstractmethod
    def get_latest_bars(self, symbols: Sequence[str]) -> Dict[str, Bar]:
        raise NotImplementedError

    @abstractmethod
    def get_market_calendar(self, start: datetime, end: datetime) -> List[Mapping[str, object]]:
        raise NotImplementedError

    @abstractmethod
    def get_snapshots(self, symbols: Sequence[str]) -> Dict[str, Mapping[str, object]]:
        raise NotImplementedError

    @abstractmethod
    def stream_bars(self, symbols: Sequence[str], on_message: ProviderMessageHandler) -> None:
        raise NotImplementedError

    @abstractmethod
    def stream_trades(self, symbols: Sequence[str], on_message: ProviderMessageHandler) -> None:
        raise NotImplementedError

    @abstractmethod
    def stream_quotes(self, symbols: Sequence[str], on_message: ProviderMessageHandler) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_historical_news(
        self,
        symbols: Sequence[str],
        start: datetime,
        end: datetime,
    ) -> Dict[str, List[Mapping[str, object]]]:
        raise NotImplementedError

    @abstractmethod
    def stream_news(self, symbols: Sequence[str], on_message: ProviderMessageHandler) -> None:
        raise NotImplementedError


def chunk_symbols(symbols: Iterable[str], chunk_size: int = 100) -> List[List[str]]:
    cleaned = [symbol.upper().strip() for symbol in symbols if symbol and symbol.strip()]
    return [cleaned[i : i + chunk_size] for i in range(0, len(cleaned), chunk_size)]
