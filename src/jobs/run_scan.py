from __future__ import annotations

from typing import Mapping

from src.config import AppSettings, get_settings
from src.features.acceleration import compute_acceleration
from src.features.breakout import breakout_strength
from src.features.catalyst import catalyst_signal
from src.features.liquidity import liquidity_quality
from src.features.returns import day_percent_change, rolling_return
from src.features.reversal_risk import reversal_risk_score, short_term_volatility, wick_rejection_score
from src.features.rvol import compute_rvol
from src.features.vwap import compute_vwap, distance_from_vwap_pct
from src.providers.alpaca_provider import AlpacaProvider
from src.providers.base import BaseMarketDataProvider
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
    settings: AppSettings | None = None,
    persist: bool = True,
) -> dict[str, object]:
    settings = settings or get_settings()
    provider = provider or AlpacaProvider(settings)
    settings_snapshot = build_settings_snapshot(settings)
    universe = build_universe(provider=provider, settings=settings)
    symbols = [str(row["symbol"]).upper() for row in universe]
    fundamentals = {str(row["symbol"]).upper(): row for row in universe}
    start, end = utc_window(90)

    bars_by_symbol = provider.get_historical_bars(symbols, "1Min", start, end)
    snapshots = provider.get_snapshots(symbols)

    coarse_rows = [
        _features_for_symbol(
            symbol,
            bars_by_symbol.get(symbol, []),
            snapshots.get(symbol, {}),
            [],
            fundamentals.get(symbol, {}),
            settings,
            settings_snapshot,
        )
        for symbol in symbols
    ]
    coarse_rows = [row for row in coarse_rows if row]
    coarse_rows.sort(key=lambda row: float(row["score"]), reverse=True)

    news_candidate_count = min(len(coarse_rows), max(settings.shortlist_size * 2, settings.basic_news_candidate_count))
    news_symbols = [str(row["ticker"]) for row in coarse_rows[:news_candidate_count]]
    news_by_symbol = provider.get_historical_news(news_symbols, start, end) if news_symbols else {}
    if news_by_symbol:
        row_by_symbol = {str(row["ticker"]): row for row in coarse_rows}
        for symbol in news_symbols:
            row_by_symbol[symbol] = _features_for_symbol(
                symbol,
                bars_by_symbol.get(symbol, []),
                snapshots.get(symbol, {}),
                news_by_symbol.get(symbol, []),
                fundamentals.get(symbol, {}),
                settings,
                settings_snapshot,
            )
        coarse_rows = [row for row in row_by_symbol.values() if row]
        coarse_rows.sort(key=lambda row: float(row["score"]), reverse=True)

    shortlist_size = min(settings.shortlist_size, 30)
    shortlist = coarse_rows[:shortlist_size]
    trade_card = generate_trade_card(shortlist, settings)
    trade_card_dict = trade_card.as_dict() if trade_card else None
    if persist:
        save_scan(shortlist, trade_card_dict)
    return {
        "rows": shortlist,
        "trade_card": trade_card_dict,
        "universe_count": len(universe),
        "feed": settings.alpaca_feed.lower(),
        "data_confidence": "Basic/IEX" if settings.alpaca_feed.lower() == "iex" else "SIP/Plus",
        "settings_snapshot": settings_snapshot,
    }


def _features_for_symbol(
    symbol: str,
    bars: list[Mapping[str, object]],
    snapshot: Mapping[str, object],
    news_items: list[Mapping[str, object]],
    fundamentals: Mapping[str, object],
    settings: AppSettings,
    settings_snapshot: Mapping[str, object],
) -> dict[str, object]:
    if len(bars) < 10:
        return {}
    price = float((snapshot.get("latestTrade") or {}).get("p") or bars[-1].get("c") or 0)
    avg_daily_volume = float(fundamentals.get("avg_daily_volume") or 0)
    vwap = compute_vwap(bars)
    liquidity = liquidity_quality(snapshot, avg_daily_volume)
    has_catalyst, catalyst_summary, catalyst_score = catalyst_signal(news_items)
    features = {
        "ticker": symbol,
        "feed": settings.alpaca_feed.lower(),
        "data_confidence": "Basic/IEX" if settings.alpaca_feed.lower() == "iex" else "SIP/Plus",
        "limitations": "Not consolidated SIP tape" if settings.alpaca_feed.lower() == "iex" else "Consolidated SIP feed",
        "settings_snapshot": dict(settings_snapshot),
        "price": price,
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
        "has_catalyst": has_catalyst,
        "catalyst_summary": catalyst_summary,
        "catalyst_score": catalyst_score,
        "spread_liquidity_quality": liquidity,
        "liquidity_quality": liquidity,
    }
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
