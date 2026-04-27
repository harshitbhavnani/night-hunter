from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping

from src.config import AppSettings, get_settings
from src.features.acceleration import compute_acceleration
from src.features.breakout import breakout_strength
from src.features.liquidity import crypto_liquidity_quality, orderbook_depth_metrics, spread_pct_from_snapshot
from src.features.returns import day_percent_change, rolling_return
from src.features.reversal_risk import reversal_risk_score, short_term_volatility, wick_rejection_score
from src.features.rvol import compute_rvol
from src.features.vwap import compute_vwap, distance_from_vwap_pct
from src.providers.alpaca_provider import AlpacaProvider
from src.providers.base import BaseMarketDataProvider
from src.providers.robinhood_crypto_provider import RobinhoodCryptoProvider
from src.scoring.execution_engine import build_execution_candidate, generate_trade_card
from src.scoring.phase_engine import classify_phase
from src.scoring.score_engine import compute_momentum_score
from src.scoring.veto_engine import apply_veto_logic
from src.settings_snapshot import build_settings_snapshot
from src.storage.repositories import save_scan
from src.universe.build_universe import build_universe
from src.utils.timeframes import utc_window


def run_scan(
    provider: BaseMarketDataProvider | None = None,
    robinhood_provider: object | None = None,
    settings: AppSettings | None = None,
    persist: bool = True,
    force_refresh_universe: bool = False,
) -> dict[str, object]:
    settings = settings or get_settings()
    provider = provider or AlpacaProvider(settings)
    settings_snapshot = build_settings_snapshot(settings)
    diagnostics: dict[str, object] = {
        "feed": "crypto",
        "data_confidence": "Alpaca Crypto",
        "limitations": "Venue-specific crypto data; not consolidated global tape.",
    }
    universe = build_universe(
        provider=provider,
        settings=settings,
        use_cache=not force_refresh_universe,
        diagnostics=diagnostics,
    )
    symbols = [str(row["symbol"]).upper() for row in universe]
    fundamentals = {str(row["symbol"]).upper(): row for row in universe}
    start, end = utc_window(settings.crypto_scan_minutes)
    diagnostics.update(
        {
            "scan_mode": "crypto_rolling",
            "scan_window_label": f"Rolling crypto window: last {settings.crypto_scan_minutes} minutes",
            "scan_window_start": start.isoformat(),
            "scan_window_end": end.isoformat(),
        }
    )

    bars_by_symbol = provider.get_historical_bars(symbols, "1Min", start, end) if symbols else {}
    snapshots = provider.get_snapshots(symbols) if symbols else {}
    orderbooks = provider.get_orderbooks(symbols) if symbols else {}
    rh_products, rh_quotes = _robinhood_venue_data(symbols, robinhood_provider, settings, diagnostics)
    diagnostics["symbols_with_1min_bars"] = sum(1 for bars in bars_by_symbol.values() if bars)
    diagnostics["alpaca_orderbook_count"] = len(orderbooks)

    coarse_rows = [
        _features_for_symbol(
            symbol,
            bars_by_symbol.get(symbol, []),
            snapshots.get(symbol, {}),
            orderbooks.get(symbol, {}),
            rh_quotes.get(symbol, {}),
            rh_products.get(symbol, {}),
            [],
            fundamentals.get(symbol, {}),
            settings,
            settings_snapshot,
        )
        for symbol in symbols
    ]
    coarse_rows = [row for row in coarse_rows if row]
    diagnostics["feature_rows"] = len(coarse_rows)
    liquidity_rows = _apply_crypto_liquidity_gates(coarse_rows, settings, diagnostics)
    liquidity_rows.sort(key=lambda row: float(row["score"]), reverse=True)

    diagnostics["news_symbols_fetched"] = 0

    shortlist_size = min(settings.shortlist_size, 30)
    shortlist = liquidity_rows[:shortlist_size]
    diagnostics["shortlist_size"] = len(shortlist)
    trade_card = generate_trade_card(shortlist, settings)
    trade_card_dict = trade_card.as_dict() if trade_card else None
    if persist:
        save_scan(shortlist, trade_card_dict)
    return {
        "rows": shortlist,
        "trade_card": trade_card_dict,
        "universe_count": len(universe),
        "feed": "crypto",
        "data_confidence": "Alpaca Crypto",
        "settings_snapshot": settings_snapshot,
        "diagnostics": diagnostics,
    }


def _features_for_symbol(
    symbol: str,
    bars: list[Mapping[str, object]],
    snapshot: Mapping[str, object],
    orderbook: Mapping[str, object],
    robinhood_quote: Mapping[str, object],
    robinhood_product: Mapping[str, object],
    news_items: list[Mapping[str, object]],
    fundamentals: Mapping[str, object],
    settings: AppSettings,
    settings_snapshot: Mapping[str, object],
) -> dict[str, object]:
    if len(bars) < 10:
        return {}
    price = float((snapshot.get("latestTrade") or {}).get("p") or bars[-1].get("c") or 0)
    avg_daily_volume = float(fundamentals.get("avg_daily_volume") or 0)
    dollar_volume = float(fundamentals.get("dollar_volume") or 0)
    quote_volume_window = sum(float(bar.get("v", 0) or 0) * float(bar.get("c", 0) or 0) for bar in bars)
    vwap = compute_vwap(bars)
    liquidity = crypto_liquidity_quality(snapshot, quote_volume_window, settings.crypto_min_quote_volume)
    spread_pct = spread_pct_from_snapshot(snapshot)
    depth_metrics = orderbook_depth_metrics(orderbook, settings.crypto_depth_bps)
    depth_notional = float(depth_metrics.get("alpaca_depth_notional", 0) or 0)
    features = {
        "ticker": symbol,
        "asset_class": "crypto",
        "feed": "crypto",
        "data_confidence": "Alpaca Crypto",
        "limitations": "Venue-specific crypto data; not consolidated global tape.",
        "settings_snapshot": dict(settings_snapshot),
        "price": price,
        "avg_daily_volume": avg_daily_volume,
        "avg_daily_volume_source": fundamentals.get("avg_daily_volume_source", "alpaca_crypto"),
        "dollar_volume": dollar_volume,
        "quote_volume": quote_volume_window,
        "day_change_pct": day_percent_change(snapshot, bars),
        "return_5m": rolling_return(bars, 5),
        "return_15m": rolling_return(bars, 15),
        "return_30m": rolling_return(bars, 30),
        "rvol": compute_rvol(bars, avg_daily_volume),
        "acceleration": compute_acceleration(bars),
        "vwap": vwap,
        "distance_from_vwap_pct": distance_from_vwap_pct(price, vwap),
        "breakout_strength": breakout_strength(bars),
        "wick_rejection_score": wick_rejection_score(bars),
        "short_term_volatility": short_term_volatility(bars),
        "has_catalyst": False,
        "catalyst_summary": "Crypto mode: structure-only setup; no catalyst required.",
        "catalyst_score": 0.0,
        "spread_pct": spread_pct,
        "alpaca_spread_pct": spread_pct,
        "spread_liquidity_quality": liquidity,
        "liquidity_quality": liquidity,
        **depth_metrics,
        "alpaca_depth_proxy_ok": depth_notional >= settings.crypto_min_orderbook_notional_depth,
    }
    features.update(_robinhood_features(symbol, price, robinhood_quote, robinhood_product, settings))
    features["reversal_risk"] = reversal_risk_score(bars, price, vwap, liquidity)
    score = compute_momentum_score(features, settings.score_weights)
    features["score"] = score.total
    features["score_breakdown"] = score.as_dict()
    features["phase"] = classify_phase(features)
    execution_candidate = build_execution_candidate(features)
    veto = apply_veto_logic(execution_candidate, settings)
    features["verdict"] = veto.verdict
    features["veto_reasons"] = veto.reasons
    return features


def _apply_crypto_liquidity_gates(
    rows: list[dict[str, object]],
    settings: AppSettings,
    diagnostics: dict[str, object],
) -> list[dict[str, object]]:
    quote_rows = [
        row for row in rows if float(row.get("quote_volume", 0) or 0) >= settings.crypto_min_quote_volume
    ]
    spread_rows = [
        row for row in quote_rows if float(row.get("spread_pct", 999) or 999) <= settings.crypto_max_spread_pct
    ]
    depth_rows = [
        row
        for row in spread_rows
        if float(row.get("alpaca_depth_notional", 0) or 0) >= settings.crypto_min_orderbook_notional_depth
    ]
    rh_tradable_rows = [row for row in depth_rows if bool(row.get("rh_tradable", False))]
    rh_spread_rows = [
        row
        for row in rh_tradable_rows
        if float(row.get("rh_spread_pct", 999) or 999) <= settings.robinhood_max_spread_pct
    ]
    rh_gate_applied = diagnostics.get("robinhood_quote_status") == "ok"
    diagnostics.update(
        {
            "quote_volume_eligible_count": len(quote_rows),
            "alpaca_spread_eligible_count": len(spread_rows),
            "alpaca_depth_eligible_count": len(depth_rows),
            "robinhood_tradable_count": len(rh_tradable_rows),
            "robinhood_spread_eligible_count": len(rh_spread_rows),
            "robinhood_gate_applied": rh_gate_applied,
            "final_trading_universe_size": len(rh_spread_rows if rh_gate_applied else depth_rows),
        }
    )
    return rh_spread_rows if rh_gate_applied else depth_rows


def _robinhood_venue_data(
    symbols: list[str],
    robinhood_provider: object | None,
    settings: AppSettings,
    diagnostics: dict[str, object],
) -> tuple[dict[str, Mapping[str, object]], dict[str, Mapping[str, object]]]:
    diagnostics["robinhood_quote_gate_enabled"] = settings.robinhood_quote_gate_enabled
    diagnostics["robinhood_credentials_loaded"] = settings.robinhood_quote_gate_ready
    diagnostics["robinhood_quote_count"] = 0
    diagnostics["robinhood_product_count"] = 0
    if not settings.robinhood_quote_gate_enabled or not symbols:
        diagnostics["robinhood_quote_status"] = "disabled"
        return {}, {}
    if robinhood_provider is None and not settings.robinhood_quote_gate_ready:
        diagnostics["robinhood_quote_status"] = "missing_credentials"
        return {}, {}

    provider = robinhood_provider or RobinhoodCryptoProvider(settings)
    try:
        products = dict(provider.get_products(symbols))  # type: ignore[attr-defined]
        quotes = dict(provider.get_quotes(symbols))  # type: ignore[attr-defined]
    except Exception as exc:
        diagnostics["robinhood_quote_status"] = "error"
        diagnostics["robinhood_quote_error"] = str(exc)
        return {}, {}

    diagnostics["robinhood_quote_status"] = "ok"
    diagnostics["robinhood_product_count"] = len(products)
    diagnostics["robinhood_quote_count"] = len(quotes)
    return products, quotes


def _robinhood_features(
    symbol: str,
    alpaca_price: float,
    quote: Mapping[str, object],
    product: Mapping[str, object],
    settings: AppSettings,
) -> dict[str, object]:
    status = "disabled" if not settings.robinhood_quote_gate_enabled else "missing_credentials"
    if quote:
        status = "ok"
    elif settings.robinhood_quote_gate_ready:
        status = "missing_quote"

    bid = _float_value(quote.get("bid"))
    ask = _float_value(quote.get("ask"))
    mid = _float_value(quote.get("mid")) or ((bid + ask) / 2 if bid > 0 and ask > 0 else 0.0)
    spread_pct = _float_value(quote.get("spread_pct")) if quote else 999.0
    quote_time = str(quote.get("quote_time") or "")
    quote_age = _quote_age_seconds(quote_time) if quote_time else None
    tradable = bool(product.get("tradable")) if product else False
    deviation = abs(alpaca_price - mid) / alpaca_price * 100 if alpaca_price > 0 and mid > 0 else 999.0
    snapshot = {
        "symbol": symbol,
        "rh_symbol": quote.get("rh_symbol") or product.get("rh_symbol"),
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "spread_pct": spread_pct,
        "quote_time": quote_time,
        "quote_age_seconds": quote_age,
        "tradable": tradable,
        "status": status,
        "alpaca_price": alpaca_price,
        "alpaca_rh_price_deviation_pct": deviation,
    }
    return {
        "rh_bid": bid,
        "rh_ask": ask,
        "rh_mid": mid,
        "rh_spread_pct": spread_pct,
        "rh_quote_time": quote_time,
        "rh_quote_age_seconds": quote_age,
        "rh_tradable": tradable,
        "rh_quote_status": status,
        "robinhood_quote_snapshot": snapshot,
        "alpaca_rh_price_deviation_pct": deviation,
    }


def _quote_age_seconds(value: str) -> float | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return round((datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds(), 3)


def _float_value(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
