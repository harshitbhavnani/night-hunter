from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Mapping

from src.config import AppSettings, get_settings
from src.providers.alpaca_provider import AlpacaProvider
from src.providers.base import BaseMarketDataProvider
from src.storage.repositories import get_universe_cache_record, save_universe_cache
from src.universe.filters import is_common_stock, max_universe_symbols, passes_universe_filters, volume_floor
from src.utils.timeframes import utc_window


def build_universe(
    provider: BaseMarketDataProvider | None = None,
    settings: AppSettings | None = None,
    use_cache: bool = True,
    diagnostics: dict[str, object] | None = None,
) -> List[Dict[str, object]]:
    """Build the real-data v1 universe from Alpaca Free data only.

    Alpaca Free does not include market cap fundamentals, so v1 filters by
    tradability, instrument type, price, ADV, and liquidity instead.
    """

    settings = settings or get_settings()
    provider = provider or AlpacaProvider(settings)
    diagnostics = diagnostics if diagnostics is not None else {}
    feed = settings.alpaca_feed.lower()
    floor = volume_floor(settings)
    max_symbols = max_universe_symbols(settings)
    cache_key = _cache_key(settings)
    diagnostics.update(
        {
            "feed": feed,
            "volume_floor": floor,
            "max_universe_symbols": max_symbols,
            "cache_key": cache_key,
            "cache_source": "miss",
        }
    )
    if use_cache:
        cached = get_universe_cache_record(cache_key)
        if cached and cached["rows"]:
            cached_diagnostics = cached.get("diagnostics", {})
            if isinstance(cached_diagnostics, Mapping):
                diagnostics.update(cached_diagnostics)
            diagnostics.update(
                {
                    "cache_source": "hit",
                    "cache_created_at": cached.get("created_at"),
                    "cache_age_minutes": _cache_age_minutes(cached.get("created_at")),
                    "universe_size": len(cached["rows"]),
                }
            )
            return list(cached["rows"])

    raw_assets = [dict(asset) for asset in provider.get_assets()]
    assets = [asset for asset in raw_assets if is_common_stock(asset)]
    symbols = [str(asset["symbol"]).upper() for asset in assets if asset.get("symbol")]
    diagnostics.update(
        {
            "cache_source": "refresh",
            "assets_loaded": len(raw_assets),
            "common_stock_count": len(assets),
        }
    )
    if not symbols:
        diagnostics.update({"price_eligible_count": 0, "volume_eligible_count": 0, "universe_size": 0})
        return []

    end = utc_window(1)[1]
    start = end - timedelta(days=45)
    daily_bars = provider.get_historical_bars(symbols, "1Day", start, end)

    rows: List[Dict[str, object]] = []
    price_eligible_count = 0
    for asset in assets:
        symbol = str(asset.get("symbol", "")).upper()
        price = _daily_close(daily_bars.get(symbol, []))
        avg_daily_volume = _average_daily_volume(daily_bars.get(symbol, []))
        if 2 <= price <= 50:
            price_eligible_count += 1
        row = {
            **asset,
            "symbol": symbol,
            "price": price,
            "avg_daily_volume": avg_daily_volume,
            "avg_daily_volume_source": "iex" if feed == "iex" else "sip",
            "dollar_volume": price * avg_daily_volume,
        }
        if passes_universe_filters(row, settings):
            rows.append(row)
    rows.sort(key=lambda row: float(row.get("dollar_volume", 0)), reverse=True)
    volume_eligible_count = len(rows)
    if max_symbols is not None:
        rows = rows[:max_symbols]
    build_diagnostics = {
        "feed": feed,
        "volume_floor": floor,
        "max_universe_symbols": max_symbols,
        "assets_loaded": len(raw_assets),
        "common_stock_count": len(assets),
        "price_eligible_count": price_eligible_count,
        "volume_eligible_count": volume_eligible_count,
        "universe_size": len(rows),
    }
    diagnostics.update(build_diagnostics)
    save_universe_cache(cache_key, rows, build_diagnostics)
    return rows


def _cache_key(settings: AppSettings) -> str:
    today = datetime.now(timezone.utc).date().isoformat()
    feed = settings.alpaca_feed.lower()
    floor = int(volume_floor(settings))
    max_symbols = max_universe_symbols(settings) or "all"
    return f"universe:{feed}:{floor}:{max_symbols}:{today}"


def _cache_age_minutes(created_at: object) -> float | None:
    if not created_at:
        return None
    try:
        parsed = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return round((datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds() / 60, 2)


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
