from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Mapping

from src.config import AppSettings, get_settings
from src.providers.alpaca_provider import AlpacaProvider
from src.providers.base import BaseMarketDataProvider
from src.storage.repositories import get_universe_cache_record, save_universe_cache
from src.utils.timeframes import utc_window


def build_universe(
    provider: BaseMarketDataProvider | None = None,
    settings: AppSettings | None = None,
    use_cache: bool = True,
    diagnostics: dict[str, object] | None = None,
) -> List[Dict[str, object]]:
    """Build the active crypto pair universe from Alpaca crypto data only."""

    settings = settings or get_settings()
    provider = provider or AlpacaProvider(settings)
    diagnostics = diagnostics if diagnostics is not None else {}
    cache_key = _cache_key(settings)
    diagnostics.update(
        {
            "feed": "crypto",
            "data_confidence": "Alpaca Crypto",
            "crypto_universe_mode": settings.crypto_universe_mode,
            "safe_fallback_used": False,
            "min_quote_volume": settings.crypto_min_quote_volume,
            "max_spread_pct": settings.crypto_max_spread_pct,
            "min_orderbook_notional_depth": settings.crypto_min_orderbook_notional_depth,
            "depth_bps": settings.crypto_depth_bps,
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

    assets, raw_assets, fallback_used, discovery_error = _discover_crypto_assets(provider, settings)
    symbols = [str(asset["symbol"]).upper() for asset in assets if asset.get("symbol")]
    diagnostics.update(
        {
            "cache_source": "refresh",
            "assets_loaded": len(raw_assets),
            "total_alpaca_crypto_assets": len([asset for asset in raw_assets if _is_crypto_asset(asset)]),
            "configured_pair_count": len(settings.crypto_symbols),
            "usd_pair_count": len(assets),
            "safe_fallback_used": fallback_used,
            "universe_source": "safe_fallback" if fallback_used else "dynamic_alpaca",
        }
    )
    if discovery_error:
        diagnostics["asset_discovery_error"] = discovery_error
    if not symbols:
        diagnostics.update(
            {
                "pairs_with_daily_bars": 0,
                "quote_volume_eligible_count": 0,
                "volume_eligible_count": 0,
                "universe_size": 0,
            }
        )
        return []

    end = utc_window(1)[1]
    start = end - timedelta(days=7)
    daily_bars = provider.get_historical_bars(symbols, "1Day", start, end)

    rows: List[Dict[str, object]] = []
    pairs_with_daily_bars = 0
    safe_fallback_symbols = {_normalize_usd_symbol(symbol) for symbol in settings.crypto_symbols}
    safe_fallback_symbols.discard("")
    safe_fallback_pairs_included = 0
    for asset in assets:
        symbol = str(asset.get("symbol", "")).upper()
        symbol_bars = daily_bars.get(symbol, [])
        price = _daily_close(symbol_bars)
        avg_base_volume = _average_daily_volume(symbol_bars)
        quote_volume = price * avg_base_volume
        is_safe_fallback = symbol in safe_fallback_symbols
        if price > 0 and avg_base_volume > 0:
            pairs_with_daily_bars += 1
        row = {
            **asset,
            "symbol": symbol,
            "price": price,
            "avg_daily_volume": avg_base_volume,
            "avg_daily_volume_source": "alpaca_crypto",
            "quote_volume": quote_volume,
            "dollar_volume": quote_volume,
            "asset_class": "crypto",
            "safe_fallback_pair": is_safe_fallback,
        }
        if price > 0 and (quote_volume >= settings.crypto_min_quote_volume or (is_safe_fallback and quote_volume > 0)):
            if is_safe_fallback and quote_volume < settings.crypto_min_quote_volume:
                safe_fallback_pairs_included += 1
            rows.append(row)
    rows.sort(key=lambda row: float(row.get("dollar_volume", 0)), reverse=True)
    volume_eligible_count = len(rows)
    build_diagnostics = {
        "feed": "crypto",
        "data_confidence": "Alpaca Crypto",
        "crypto_universe_mode": settings.crypto_universe_mode,
        "safe_fallback_used": fallback_used,
        "universe_source": "safe_fallback" if fallback_used else "dynamic_alpaca",
        "min_quote_volume": settings.crypto_min_quote_volume,
        "max_spread_pct": settings.crypto_max_spread_pct,
        "min_orderbook_notional_depth": settings.crypto_min_orderbook_notional_depth,
        "depth_bps": settings.crypto_depth_bps,
        "assets_loaded": len(raw_assets),
        "total_alpaca_crypto_assets": len([asset for asset in raw_assets if _is_crypto_asset(asset)]),
        "configured_pair_count": len(settings.crypto_symbols),
        "usd_pair_count": len(assets),
        "pairs_with_daily_bars": pairs_with_daily_bars,
        "daily_quote_volume_eligible_count": volume_eligible_count,
        "quote_volume_eligible_count": volume_eligible_count,
        "volume_eligible_count": volume_eligible_count,
        "safe_fallback_pairs_included": safe_fallback_pairs_included,
        "universe_size": len(rows),
    }
    if discovery_error:
        build_diagnostics["asset_discovery_error"] = discovery_error
    diagnostics.update(build_diagnostics)
    if rows:
        save_universe_cache(cache_key, rows, build_diagnostics)
    return rows


def _cache_key(settings: AppSettings) -> str:
    today = datetime.now(timezone.utc).date().isoformat()
    symbols = "-".join(symbol.replace("/", "") for symbol in settings.crypto_symbols)
    return (
        f"universe:v3:crypto:{settings.crypto_location}:"
        f"{settings.crypto_universe_mode}:{int(settings.crypto_min_quote_volume)}:"
        f"{settings.shortlist_size}:{symbols}:{today}"
    )


def _discover_crypto_assets(
    provider: BaseMarketDataProvider,
    settings: AppSettings,
) -> tuple[list[dict[str, object]], list[dict[str, object]], bool, str | None]:
    mode = settings.crypto_universe_mode.lower()
    if mode == "fixed":
        return _safe_fallback_assets(settings), [], True, None

    try:
        raw_assets = [dict(asset) for asset in provider.get_assets()]
    except Exception as exc:
        return _safe_fallback_assets(settings), [], True, str(exc)

    assets = [_normalized_asset(asset) for asset in raw_assets]
    assets = [asset for asset in assets if asset]
    if assets:
        return assets, raw_assets, False, None
    if mode == "dynamic_safe_fallback":
        return _safe_fallback_assets(settings), raw_assets, True, None
    return [], raw_assets, False, None


def _safe_fallback_assets(settings: AppSettings) -> list[dict[str, object]]:
    return [
        {
            "symbol": _normalize_usd_symbol(symbol),
            "name": _normalize_usd_symbol(symbol),
            "asset_class": "crypto",
            "status": "active",
            "tradable": True,
            "exchange": f"alpaca_crypto_{settings.crypto_location}",
        }
        for symbol in settings.crypto_symbols
        if _normalize_usd_symbol(symbol) and not _is_stablecoin_symbol(_normalize_usd_symbol(symbol))
    ]


def _normalized_asset(asset: Mapping[str, object]) -> dict[str, object] | None:
    if not _is_crypto_asset(asset):
        return None
    symbol = _normalize_usd_symbol(asset.get("symbol"))
    if not symbol:
        return None
    if _is_stablecoin_symbol(symbol):
        return None
    if not _is_active(asset) or not _is_tradable(asset):
        return None
    normalized = dict(asset)
    normalized["symbol"] = symbol
    normalized["asset_class"] = "crypto"
    normalized["status"] = str(asset.get("status") or "active").lower()
    normalized["tradable"] = True
    return normalized


def _is_crypto_asset(asset: Mapping[str, object]) -> bool:
    asset_class = str(asset.get("asset_class") or asset.get("class") or "").lower()
    return asset_class == "crypto"


def _is_active(asset: Mapping[str, object]) -> bool:
    status = str(asset.get("status") or asset.get("state") or "active").lower()
    return status not in {"inactive", "disabled", "delisted"}


def _is_tradable(asset: Mapping[str, object]) -> bool:
    value = asset.get("tradable", True)
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def _normalize_usd_symbol(value: object) -> str:
    raw = str(value or "").strip().upper().replace("-", "/")
    if not raw:
        return ""
    if "/" in raw:
        base, quote = raw.split("/", 1)
        return f"{base}/USD" if base and quote == "USD" else ""
    if raw.endswith("USD") and len(raw) > 3:
        return f"{raw[:-3]}/USD"
    return ""


def _is_stablecoin_symbol(symbol: str) -> bool:
    base = symbol.split("/", 1)[0].upper()
    return base in {"USDC", "USDT", "DAI", "USDG", "PYUSD", "USDP", "TUSD", "GUSD", "FDUSD", "USDE"}


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
