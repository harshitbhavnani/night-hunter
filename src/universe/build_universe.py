from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Mapping

from src.config import AppSettings, get_settings
from src.providers.alpaca_provider import AlpacaProvider
from src.providers.base import BaseMarketDataProvider
from src.storage.repositories import get_universe_cache, save_universe_cache
from src.universe.filters import is_common_stock, passes_universe_filters
from src.utils.timeframes import utc_window


def build_universe(
    provider: BaseMarketDataProvider | None = None,
    settings: AppSettings | None = None,
    use_cache: bool = True,
) -> List[Dict[str, object]]:
    """Build the real-data v1 universe from Alpaca Free data only.

    Alpaca Free does not include market cap fundamentals, so v1 filters by
    tradability, instrument type, price, ADV, and liquidity instead.
    """

    settings = settings or get_settings()
    provider = provider or AlpacaProvider(settings)
    cache_key = _cache_key(settings.alpaca_feed)
    if use_cache:
        cached = get_universe_cache(cache_key)
        if cached is not None:
            return cached

    assets = [dict(asset) for asset in provider.get_assets() if is_common_stock(asset)]
    symbols = [str(asset["symbol"]).upper() for asset in assets if asset.get("symbol")]
    if not symbols:
        return []

    end = utc_window(1)[1]
    start = end - timedelta(days=45)
    daily_bars = provider.get_historical_bars(symbols, "1Day", start, end)

    rows: List[Dict[str, object]] = []
    for asset in assets:
        symbol = str(asset.get("symbol", "")).upper()
        price = _daily_close(daily_bars.get(symbol, []))
        avg_daily_volume = _average_daily_volume(daily_bars.get(symbol, []))
        row = {
            **asset,
            "symbol": symbol,
            "price": price,
            "avg_daily_volume": avg_daily_volume,
        }
        if passes_universe_filters(row):
            rows.append(row)
    rows.sort(key=lambda row: float(row.get("avg_daily_volume", 0)), reverse=True)
    save_universe_cache(cache_key, rows)
    return rows


def _cache_key(feed: str) -> str:
    today = datetime.now(timezone.utc).date().isoformat()
    return f"universe:{feed.lower()}:{today}"


def _daily_close(bars: list[Mapping[str, object]]) -> float:
    for bar in reversed(bars):
        try:
            price = float(bar.get("c") or 0)
        except (AttributeError, TypeError, ValueError):
            price = 0.0
        if price > 0:
            return price
    return 0.0


def _average_daily_volume(bars: list[Mapping[str, object]]) -> float:
    volumes = [float(bar.get("v", 0) or 0) for bar in bars[-30:] if float(bar.get("v", 0) or 0) > 0]
    return sum(volumes) / len(volumes) if volumes else 0.0
