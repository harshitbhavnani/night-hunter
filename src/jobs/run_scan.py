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
from src.providers.kraken_venue_provider import KrakenVenueProvider
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
    venue_provider: object | None = None,
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
    rolling_min_quote_volume = _rolling_min_quote_volume(settings)
    diagnostics.update(
        {
            "scan_mode": "crypto_rolling",
            "scan_window_label": f"Rolling crypto window: last {settings.crypto_scan_minutes} minutes",
            "scan_window_start": start.isoformat(),
            "scan_window_end": end.isoformat(),
            "rolling_min_quote_volume": rolling_min_quote_volume,
        }
    )

    bars_by_symbol = provider.get_historical_bars(symbols, "1Min", start, end) if symbols else {}
    snapshots = provider.get_snapshots(symbols) if symbols else {}
    orderbooks = provider.get_orderbooks(symbols) if symbols else {}
    venue_products, venue_quotes, venue_orderbooks = _venue_data(symbols, venue_provider, settings, diagnostics)
    diagnostics["symbols_with_1min_bars"] = sum(1 for bars in bars_by_symbol.values() if bars)
    diagnostics["alpaca_orderbook_count"] = len(orderbooks)
    market_regime = _market_regime(bars_by_symbol)
    diagnostics.update(
        {
            "market_regime": market_regime["market_regime"],
            "btc_return_15m": market_regime["btc_return_15m"],
            "btc_return_30m": market_regime["btc_return_30m"],
            "eth_return_15m": market_regime["eth_return_15m"],
            "eth_return_30m": market_regime["eth_return_30m"],
        }
    )

    coarse_rows = [
        _features_for_symbol(
            symbol,
            bars_by_symbol.get(symbol, []),
            snapshots.get(symbol, {}),
            orderbooks.get(symbol, {}),
            venue_quotes.get(symbol, {}),
            venue_products.get(symbol, {}),
            venue_orderbooks.get(symbol, {}),
            [],
            fundamentals.get(symbol, {}),
            settings,
            settings_snapshot,
            market_regime,
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
    venue_quote: Mapping[str, object],
    venue_product: Mapping[str, object],
    venue_orderbook: Mapping[str, object],
    news_items: list[Mapping[str, object]],
    fundamentals: Mapping[str, object],
    settings: AppSettings,
    settings_snapshot: Mapping[str, object],
    market_regime: Mapping[str, object],
) -> dict[str, object]:
    if len(bars) < 10:
        return {}
    price = float((snapshot.get("latestTrade") or {}).get("p") or bars[-1].get("c") or 0)
    avg_daily_volume = float(fundamentals.get("avg_daily_volume") or 0)
    dollar_volume = float(fundamentals.get("dollar_volume") or 0)
    alpaca_quote_volume_window = sum(float(bar.get("v", 0) or 0) * float(bar.get("c", 0) or 0) for bar in bars)
    vwap = compute_vwap(bars)
    rolling_min_quote_volume = _rolling_min_quote_volume(settings)
    spread_pct = spread_pct_from_snapshot(snapshot)
    depth_metrics = orderbook_depth_metrics(orderbook, settings.crypto_depth_bps)
    depth_notional = float(depth_metrics.get("alpaca_depth_notional", 0) or 0)
    venue_features = _venue_features(symbol, price, venue_quote, venue_product, venue_orderbook, settings)
    venue_quote_volume_24h = _float_value(venue_features.get("venue_quote_volume_24h"))
    venue_implied_quote_volume = venue_quote_volume_24h * min(1.0, max(1, settings.crypto_scan_minutes) / 1440)
    effective_quote_volume = max(alpaca_quote_volume_window, venue_implied_quote_volume)
    liquidity = crypto_liquidity_quality(snapshot, effective_quote_volume, rolling_min_quote_volume)
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
        "quote_volume": effective_quote_volume,
        "alpaca_quote_volume": alpaca_quote_volume_window,
        "venue_implied_quote_volume": venue_implied_quote_volume,
        "rolling_min_quote_volume": rolling_min_quote_volume,
        "day_change_pct": day_percent_change(snapshot, bars),
        "return_5m": rolling_return(bars, 5),
        "return_15m": rolling_return(bars, 15),
        "return_30m": rolling_return(bars, 30),
        "rvol": compute_rvol(bars, avg_daily_volume, session_minutes=1440),
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
        "market_regime": market_regime.get("market_regime", "Unknown"),
        "btc_return_15m": market_regime.get("btc_return_15m", 0.0),
        "btc_return_30m": market_regime.get("btc_return_30m", 0.0),
        "eth_return_15m": market_regime.get("eth_return_15m", 0.0),
        "eth_return_30m": market_regime.get("eth_return_30m", 0.0),
        "regime_risk": market_regime.get("regime_risk", 0.0),
    }
    features.update(venue_features)
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
    rolling_min_quote_volume = _rolling_min_quote_volume(settings)
    quote_rows = [row for row in rows if float(row.get("quote_volume", 0) or 0) >= rolling_min_quote_volume]
    alpaca_quote_rows = [
        row for row in rows if float(row.get("alpaca_quote_volume", 0) or 0) >= rolling_min_quote_volume
    ]
    venue_implied_quote_rows = [
        row for row in rows if float(row.get("venue_implied_quote_volume", 0) or 0) >= rolling_min_quote_volume
    ]
    spread_rows = [
        row for row in quote_rows if float(row.get("spread_pct", 999) or 999) <= settings.crypto_max_spread_pct
    ]
    alpaca_depth_rows = [
        row
        for row in spread_rows
        if float(row.get("alpaca_depth_notional", 0) or 0) >= settings.crypto_min_orderbook_notional_depth
    ]
    venue_tradable_rows = [row for row in spread_rows if bool(row.get("venue_tradable", False))]
    venue_spread_rows = [
        row
        for row in venue_tradable_rows
        if float(row.get("venue_spread_pct", 999) or 999) <= settings.kraken_max_spread_pct
    ]
    venue_depth_rows = [
        row
        for row in venue_spread_rows
        if float(row.get("venue_depth_notional", 0) or 0) >= settings.kraken_min_orderbook_notional_depth
    ]
    venue_gate_applied = diagnostics.get("venue_quote_status") == "ok"
    diagnostics.update(
        {
            "quote_volume_eligible_count": len(quote_rows),
            "rolling_quote_volume_eligible_count": len(quote_rows),
            "alpaca_rolling_quote_volume_eligible_count": len(alpaca_quote_rows),
            "venue_implied_quote_volume_eligible_count": len(venue_implied_quote_rows),
            "rolling_min_quote_volume": rolling_min_quote_volume,
            "alpaca_spread_eligible_count": len(spread_rows),
            "alpaca_depth_eligible_count": len(alpaca_depth_rows),
            "venue_tradable_count": len(venue_tradable_rows),
            "venue_spread_eligible_count": len(venue_spread_rows),
            "venue_depth_eligible_count": len(venue_depth_rows),
            "venue_gate_applied": venue_gate_applied,
            "final_trading_universe_size": len(venue_depth_rows) if venue_gate_applied else 0,
        }
    )
    return venue_depth_rows if venue_depth_rows else spread_rows


def _market_regime(bars_by_symbol: Mapping[str, list[Mapping[str, object]]]) -> dict[str, object]:
    btc_bars = bars_by_symbol.get("BTC/USD", [])
    eth_bars = bars_by_symbol.get("ETH/USD", [])
    btc_15m = rolling_return(btc_bars, 15) if btc_bars else 0.0
    btc_30m = rolling_return(btc_bars, 30) if btc_bars else 0.0
    eth_15m = rolling_return(eth_bars, 15) if eth_bars else 0.0
    eth_30m = rolling_return(eth_bars, 30) if eth_bars else 0.0
    regime = "Constructive"
    risk = 0.0
    if btc_15m <= -1.25 or btc_30m <= -2.5 or (btc_15m < -0.75 and eth_15m < -1.0):
        regime = "Risk-Off"
        risk = 8.0
    elif btc_15m < -0.5 or eth_15m < -0.75:
        regime = "Caution"
        risk = 4.5
    return {
        "market_regime": regime,
        "regime_risk": risk,
        "btc_return_15m": round(btc_15m, 4),
        "btc_return_30m": round(btc_30m, 4),
        "eth_return_15m": round(eth_15m, 4),
        "eth_return_30m": round(eth_30m, 4),
    }


def _rolling_min_quote_volume(settings: AppSettings) -> float:
    window_ratio = max(1, int(settings.crypto_scan_minutes)) / 1440
    return round(max(1_000.0, settings.crypto_min_quote_volume * window_ratio), 4)


def _venue_data(
    symbols: list[str],
    venue_provider: object | None,
    settings: AppSettings,
    diagnostics: dict[str, object],
) -> tuple[dict[str, Mapping[str, object]], dict[str, Mapping[str, object]], dict[str, Mapping[str, object]]]:
    diagnostics["venue_provider"] = settings.venue_provider
    diagnostics["venue_quote_status"] = "not_requested" if not symbols else "pending"
    diagnostics["venue_quote_count"] = 0
    diagnostics["venue_product_count"] = 0
    diagnostics["venue_orderbook_count"] = 0
    if not symbols:
        diagnostics["venue_quote_status"] = "no_symbols"
        return {}, {}, {}

    provider = venue_provider or KrakenVenueProvider(settings)
    try:
        products = dict(provider.get_products(symbols))  # type: ignore[attr-defined]
        quotes = dict(provider.get_quotes(symbols))  # type: ignore[attr-defined]
        orderbooks = dict(provider.get_orderbooks(symbols))  # type: ignore[attr-defined]
    except Exception as exc:
        diagnostics["venue_quote_status"] = "error"
        diagnostics["venue_quote_error"] = str(exc)
        return {}, {}, {}

    diagnostics["venue_quote_status"] = "ok"
    diagnostics["venue_product_count"] = len(products)
    diagnostics["venue_quote_count"] = len(quotes)
    diagnostics["venue_orderbook_count"] = len(orderbooks)
    return products, quotes, orderbooks


def _venue_features(
    symbol: str,
    alpaca_price: float,
    quote: Mapping[str, object],
    product: Mapping[str, object],
    orderbook: Mapping[str, object],
    settings: AppSettings,
) -> dict[str, object]:
    status = "missing_quote"
    if quote:
        status = "ok"

    bid = _float_value(quote.get("bid"))
    ask = _float_value(quote.get("ask"))
    mid = _float_value(quote.get("mid")) or ((bid + ask) / 2 if bid > 0 and ask > 0 else 0.0)
    venue_quote_volume_24h = _venue_quote_volume_24h(quote, mid)
    spread_pct = _float_value(quote.get("spread_pct")) if quote else 999.0
    quote_time = str(quote.get("quote_time") or "")
    quote_age = _quote_age_seconds(quote_time) if quote_time else None
    tradable = bool(product.get("tradable")) if product else False
    deviation = abs(alpaca_price - mid) / alpaca_price * 100 if alpaca_price > 0 and mid > 0 else 999.0
    depth_notional = _float_value(orderbook.get("venue_depth_notional"))
    depth_bid_notional = _float_value(orderbook.get("venue_depth_bid_notional"))
    depth_ask_notional = _float_value(orderbook.get("venue_depth_ask_notional"))
    depth_bps = _float_value(orderbook.get("venue_depth_bps")) or settings.crypto_depth_bps
    venue_symbol = str(
        quote.get("venue_symbol")
        or product.get("venue_symbol")
        or orderbook.get("venue_symbol")
        or symbol
    )
    snapshot = {
        "symbol": symbol,
        "venue_name": "Kraken",
        "venue_symbol": venue_symbol,
        "kraken_pair": quote.get("kraken_pair") or product.get("kraken_pair") or orderbook.get("kraken_pair"),
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "spread_pct": spread_pct,
        "quote_time": quote_time,
        "quote_age_seconds": quote_age,
        "tradable": tradable,
        "status": status,
        "depth_notional": depth_notional,
        "depth_bid_notional": depth_bid_notional,
        "depth_ask_notional": depth_ask_notional,
        "depth_bps": depth_bps,
        "quote_volume_24h": venue_quote_volume_24h,
        "alpaca_price": alpaca_price,
        "alpaca_venue_price_deviation_pct": deviation,
    }
    return {
        "venue_name": "Kraken",
        "venue_symbol": venue_symbol,
        "venue_bid": bid,
        "venue_ask": ask,
        "venue_mid": mid,
        "venue_spread_pct": spread_pct,
        "venue_quote_time": quote_time,
        "venue_quote_age_seconds": quote_age,
        "venue_tradable": tradable,
        "venue_quote_status": status,
        "venue_depth_notional": depth_notional,
        "venue_depth_bid_notional": depth_bid_notional,
        "venue_depth_ask_notional": depth_ask_notional,
        "venue_depth_bps": depth_bps,
        "venue_quote_volume_24h": venue_quote_volume_24h,
        "venue_quote_snapshot": snapshot,
        "alpaca_venue_price_deviation_pct": deviation,
    }


def _venue_quote_volume_24h(quote: Mapping[str, object], mid: float) -> float:
    raw = quote.get("raw") if isinstance(quote, Mapping) else {}
    if not isinstance(raw, Mapping) or mid <= 0:
        return 0.0
    volume = raw.get("v")
    return max(_list_float(volume, 0), _list_float(volume, 1)) * mid


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


def _list_float(value: object, index: int) -> float:
    try:
        if isinstance(value, (list, tuple)):
            return float(value[index] or 0)
        return float(value or 0)
    except (IndexError, TypeError, ValueError):
        return 0.0
