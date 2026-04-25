from __future__ import annotations

from typing import Mapping

from src.config import AppSettings, get_settings


EXCLUDED_SYMBOL_MARKERS = ("+", "/", ".W", "-W", ".WS", "-WS", ".WTS", "-WTS", ".RT", "-RT", ".U", "-U")
EXCLUDED_NAME_MARKERS = (
    " ETF",
    " FUND",
    " WARRANT",
    " RIGHT",
    " PREFERRED",
    " PFD",
    " UNIT",
    " TRUST",
    " SPAC",
)


def is_common_stock(asset: Mapping[str, object]) -> bool:
    symbol = str(asset.get("symbol", "")).upper()
    name = str(asset.get("name", "")).upper()
    asset_class = str(asset.get("asset_class", "us_equity")).lower()
    exchange = str(asset.get("exchange", "")).upper()
    status = str(asset.get("status", "active")).lower()
    tradable = str(asset.get("tradable", True)).lower() not in {"false", "0", "no"}

    if asset_class != "us_equity" or status != "active" or not tradable:
        return False
    if exchange in {"OTC", "OTCQB", "OTCQX", "PINK"}:
        return False
    if any(marker in symbol for marker in EXCLUDED_SYMBOL_MARKERS):
        return False
    if any(marker in f" {name}" for marker in EXCLUDED_NAME_MARKERS):
        return False
    return True


def volume_floor(settings: AppSettings | None = None) -> float:
    settings = settings or get_settings()
    if settings.alpaca_feed.lower() == "iex":
        return float(settings.basic_min_iex_avg_daily_volume)
    return 500_000.0


def max_universe_symbols(settings: AppSettings | None = None) -> int | None:
    settings = settings or get_settings()
    if settings.alpaca_feed.lower() == "iex":
        return int(settings.basic_max_universe_symbols)
    return None


def passes_universe_filters(asset: Mapping[str, object], settings: AppSettings | None = None) -> bool:
    if not is_common_stock(asset):
        return False
    price = float(asset.get("price") or 0)
    avg_daily_volume = float(asset.get("avg_daily_volume") or 0)
    return 2 <= price <= 50 and avg_daily_volume >= volume_floor(settings)
