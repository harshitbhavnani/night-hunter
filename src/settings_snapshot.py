from __future__ import annotations

from src.config import AppSettings


def build_settings_snapshot(settings: AppSettings) -> dict[str, object]:
    return {
        "provider_mode": settings.provider_mode,
        "market_mode": "crypto",
        "feed": "crypto",
        "crypto_location": settings.crypto_location,
        "crypto_universe_mode": settings.crypto_universe_mode,
        "crypto_symbols": list(settings.crypto_symbols),
        "crypto_scan_minutes": settings.crypto_scan_minutes,
        "crypto_min_quote_volume": settings.crypto_min_quote_volume,
        "crypto_max_spread_pct": settings.crypto_max_spread_pct,
        "crypto_min_orderbook_notional_depth": settings.crypto_min_orderbook_notional_depth,
        "crypto_depth_bps": settings.crypto_depth_bps,
        "venue_provider": settings.venue_provider,
        "kraken_base_url": settings.kraken_base_url,
        "kraken_max_spread_pct": settings.kraken_max_spread_pct,
        "kraken_max_quote_age_seconds": settings.kraken_max_quote_age_seconds,
        "kraken_min_orderbook_notional_depth": settings.kraken_min_orderbook_notional_depth,
        "max_alpaca_venue_deviation_pct": settings.max_alpaca_venue_deviation_pct,
        "data_confidence": "Alpaca Crypto",
        "limitations": "Venue-specific crypto data; not consolidated global tape.",
        "min_score": settings.min_score,
        "shortlist_size": settings.shortlist_size,
        "max_stop_distance_pct": settings.max_stop_distance_pct,
        "min_risk_reward": settings.min_risk_reward,
        "max_vwap_extension_pct": settings.max_vwap_extension_pct,
        "mock_starting_cash": settings.mock_starting_cash,
        "score_weights": settings.score_weights.as_dict(),
    }
