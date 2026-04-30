from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path
from typing import Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st
from streamlit.errors import StreamlitAPIException

from src.analysis.calibration import scan_score_diagnostics
from src.config import AppSettings, ScoreWeights, get_settings


TABLE_COLUMNS = {
    "ticker": "Ticker",
    "price": "Price",
    "quote_volume": "Quote Volume",
    "day_change_pct": "% Day",
    "return_15m": "% 15m",
    "rvol": "RVOL",
    "acceleration": "Acceleration",
    "phase": "Phase",
    "spread_pct": "Alpaca Spread %",
    "alpaca_depth_notional": "Depth Proxy",
    "alpaca_depth_proxy_ok": "Depth OK",
    "venue_spread_pct": "Kraken Spread %",
    "venue_depth_notional": "Kraken Depth",
    "venue_tradable": "Kraken Tradable",
    "venue_quote_status": "Venue Status",
    "score": "Score",
    "verdict": "Verdict",
    "data_confidence": "Data",
}


def page_setup(title: str) -> None:
    st.set_page_config(page_title=f"Night Hunter | {title}", layout="wide")


def effective_settings() -> AppSettings:
    base = get_settings()
    payload = st.session_state.get("night_hunter_settings")
    if not payload:
        return base
    weights = ScoreWeights(
        rvol=float(payload.get("weight_rvol", base.score_weights.rvol)),
        acceleration=float(payload.get("weight_acceleration", base.score_weights.acceleration)),
        breakout_strength=float(payload.get("weight_breakout", base.score_weights.breakout_strength)),
        catalyst=float(payload.get("weight_catalyst", base.score_weights.catalyst)),
        reversal_risk=float(payload.get("weight_reversal_risk", base.score_weights.reversal_risk)),
    )
    return replace(
        base,
        min_score=float(payload.get("min_score", base.min_score)),
        shortlist_size=int(payload.get("shortlist_size", base.shortlist_size)),
        max_stop_distance_pct=float(payload.get("max_stop_distance_pct", base.max_stop_distance_pct)),
        min_risk_reward=float(payload.get("min_risk_reward", base.min_risk_reward)),
        max_vwap_extension_pct=float(payload.get("max_vwap_extension_pct", base.max_vwap_extension_pct)),
        mock_starting_cash=float(payload.get("mock_starting_cash", base.mock_starting_cash)),
        mock_fee_bps=float(payload.get("mock_fee_bps", base.mock_fee_bps)),
        mock_slippage_bps=float(payload.get("mock_slippage_bps", base.mock_slippage_bps)),
        calibration_min_trades=int(payload.get("calibration_min_trades", base.calibration_min_trades)),
        calibration_holdout_pct=float(payload.get("calibration_holdout_pct", base.calibration_holdout_pct)),
        crypto_symbols=tuple(
            symbol.strip().upper()
            for symbol in str(payload.get("crypto_symbols", ",".join(base.crypto_symbols))).split(",")
            if symbol.strip()
        )
        or base.crypto_symbols,
        crypto_universe_mode=str(payload.get("crypto_universe_mode", base.crypto_universe_mode)).lower(),
        crypto_location=str(payload.get("crypto_location", base.crypto_location)).lower(),
        crypto_scan_minutes=int(payload.get("crypto_scan_minutes", base.crypto_scan_minutes)),
        crypto_min_quote_volume=float(payload.get("crypto_min_quote_volume", base.crypto_min_quote_volume)),
        crypto_max_spread_pct=float(payload.get("crypto_max_spread_pct", base.crypto_max_spread_pct)),
        crypto_min_orderbook_notional_depth=float(
            payload.get("crypto_min_orderbook_notional_depth", base.crypto_min_orderbook_notional_depth)
        ),
        crypto_depth_bps=float(payload.get("crypto_depth_bps", base.crypto_depth_bps)),
        venue_provider=str(payload.get("venue_provider", base.venue_provider)).lower(),
        kraken_base_url=str(payload.get("kraken_base_url", base.kraken_base_url)).rstrip("/"),
        kraken_max_spread_pct=float(payload.get("kraken_max_spread_pct", base.kraken_max_spread_pct)),
        kraken_max_quote_age_seconds=int(
            payload.get("kraken_max_quote_age_seconds", base.kraken_max_quote_age_seconds)
        ),
        kraken_min_orderbook_notional_depth=float(
            payload.get("kraken_min_orderbook_notional_depth", base.kraken_min_orderbook_notional_depth)
        ),
        max_alpaca_venue_deviation_pct=float(
            payload.get("max_alpaca_venue_deviation_pct", base.max_alpaca_venue_deviation_pct)
        ),
        score_weights=weights,
    )


def provider_label(settings: AppSettings) -> str:
    return "Alpaca Crypto bars" if settings.live_data_enabled else "Not connected"


def venue_label(settings: AppSettings) -> str:
    provider = settings.venue_provider.upper() if settings.venue_provider else "None"
    return f"{provider} gate"


def universe_label(settings: AppSettings, diagnostics: Mapping[str, object] | None = None) -> str:
    diagnostics = diagnostics or {}
    source = str(diagnostics.get("universe_source") or "").lower()
    fallback_used = bool(diagnostics.get("safe_fallback_used", False))
    if source == "dynamic_alpaca" and not fallback_used:
        return "Dynamic Alpaca USD pairs"
    if source == "safe_fallback" or fallback_used:
        return "Safe fallback pairs"
    if settings.crypto_universe_mode == "fixed":
        return "Fixed fallback list"
    return "Dynamic discovery"


def universe_detail(diagnostics: Mapping[str, object] | None = None) -> str | None:
    diagnostics = diagnostics or {}
    if not diagnostics:
        return None
    discovered = diagnostics.get("usd_pair_count")
    eligible = diagnostics.get("universe_size")
    trading = diagnostics.get("final_trading_universe_size")
    parts = []
    if discovered is not None:
        parts.append(f"{int(discovered):,} discovered")
    if eligible is not None:
        parts.append(f"{int(eligible):,} volume eligible")
    if trading is not None:
        parts.append(f"{int(trading):,} trading universe")
    return " | ".join(parts) if parts else None


def scan_dataframe(rows: list[Mapping[str, object]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=list(TABLE_COLUMNS.values()))
    frame = pd.DataFrame(rows)
    for column in TABLE_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    frame = frame[list(TABLE_COLUMNS.keys())].rename(columns=TABLE_COLUMNS)
    numeric = [
        "Price",
        "Quote Volume",
        "% Day",
        "% 15m",
        "RVOL",
        "Acceleration",
        "Alpaca Spread %",
        "Depth Proxy",
        "Kraken Spread %",
        "Kraken Depth",
        "Score",
    ]
    for column in numeric:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").round(2)
    frame["Depth OK"] = frame["Depth OK"].map(lambda value: "Yes" if value else "No")
    frame["Kraken Tradable"] = frame["Kraken Tradable"].map(lambda value: "Yes" if value else "No")
    return frame


def render_shortlist_trade_card_launcher(rows: list[Mapping[str, object]], key_prefix: str) -> None:
    symbols = [str(row.get("ticker") or row.get("symbol") or "").upper() for row in rows]
    symbols = [symbol for symbol in symbols if symbol]
    if not symbols:
        return

    row_by_symbol = {
        str(row.get("ticker") or row.get("symbol") or "").upper(): row
        for row in rows
        if str(row.get("ticker") or row.get("symbol") or "")
    }

    def label(symbol: str) -> str:
        row = row_by_symbol.get(symbol, {})
        score = float(row.get("score", 0) or 0)
        return f"{symbol} | Score {score:.2f} | {row.get('phase', '')} | {row.get('verdict', '')}"

    left, right = st.columns([3, 1])
    selected = left.selectbox("Open shortlist ticker", symbols, format_func=label, key=f"{key_prefix}_trade_symbol")
    if right.button("Open Trade Card", key=f"{key_prefix}_open_trade_card", width="stretch"):
        st.session_state["selected_trade_symbol"] = selected
        _switch_to_trade_card()


def render_scan_diagnostics(result: Mapping[str, object] | None) -> None:
    diagnostics = (result or {}).get("diagnostics")
    if not isinstance(diagnostics, Mapping):
        return
    score_report = scan_score_diagnostics((result or {}).get("rows", []))

    with st.expander("Scan Diagnostics"):
        cache_source = diagnostics.get("cache_source", "unknown")
        cache_age = diagnostics.get("cache_age_minutes")
        cache_text = f"{cache_source}"
        if cache_age is not None:
            cache_text += f" ({float(cache_age):.1f} min old)"
        if diagnostics.get("scan_window_label"):
            st.caption(str(diagnostics.get("scan_window_label")))
        st.caption(f"Universe cache: {cache_text}")
        columns = st.columns(4)
        metrics = [
            ("Configured Fallback Pairs", diagnostics.get("configured_pair_count")),
            ("Alpaca Assets", diagnostics.get("total_alpaca_crypto_assets", diagnostics.get("assets_loaded"))),
            ("USD Pairs", diagnostics.get("usd_pair_count")),
            ("Pairs With Daily Bars", diagnostics.get("pairs_with_daily_bars")),
            ("Daily Vol Eligible", diagnostics.get("daily_quote_volume_eligible_count", diagnostics.get("volume_eligible_count"))),
            ("Rolling Vol OK", diagnostics.get("rolling_quote_volume_eligible_count")),
            ("Alpaca Spread OK", diagnostics.get("alpaca_spread_eligible_count")),
            ("Depth OK", diagnostics.get("alpaca_depth_eligible_count")),
            ("Kraken Tradable", diagnostics.get("venue_tradable_count")),
            ("Kraken Depth OK", diagnostics.get("venue_depth_eligible_count")),
            ("Trading Universe", diagnostics.get("final_trading_universe_size", diagnostics.get("universe_size"))),
            ("1m Bars", diagnostics.get("symbols_with_1min_bars")),
            ("Feature Rows", diagnostics.get("feature_rows")),
            ("Shortlist", diagnostics.get("shortlist_size")),
        ]
        for index, (label, value) in enumerate(metrics):
            display = "cached" if value is None else f"{int(value):,}"
            columns[index % 4].metric(label, display)

        st.write(
            {
                "feed": diagnostics.get("feed"),
                "scan_mode": diagnostics.get("scan_mode"),
                "universe_mode": diagnostics.get("crypto_universe_mode"),
                "safe_fallback_used": diagnostics.get("safe_fallback_used"),
                "universe_source": diagnostics.get("universe_source"),
                "scan_window_start": diagnostics.get("scan_window_start"),
                "scan_window_end": diagnostics.get("scan_window_end"),
                "daily_min_quote_volume": diagnostics.get("min_quote_volume"),
                "rolling_min_quote_volume": diagnostics.get("rolling_min_quote_volume"),
                "rolling_quote_volume_eligible_count": diagnostics.get("rolling_quote_volume_eligible_count"),
                "alpaca_rolling_quote_volume_eligible_count": diagnostics.get("alpaca_rolling_quote_volume_eligible_count"),
                "venue_implied_quote_volume_eligible_count": diagnostics.get("venue_implied_quote_volume_eligible_count"),
                "safe_fallback_pairs_included": diagnostics.get("safe_fallback_pairs_included"),
                "market_regime": diagnostics.get("market_regime"),
                "btc_return_15m": diagnostics.get("btc_return_15m"),
                "btc_return_30m": diagnostics.get("btc_return_30m"),
                "eth_return_15m": diagnostics.get("eth_return_15m"),
                "eth_return_30m": diagnostics.get("eth_return_30m"),
                "max_spread_pct": diagnostics.get("max_spread_pct"),
                "min_orderbook_notional_depth": diagnostics.get("min_orderbook_notional_depth"),
                "depth_bps": diagnostics.get("depth_bps"),
                "alpaca_orderbook_count": diagnostics.get("alpaca_orderbook_count"),
                "news_symbols_fetched": diagnostics.get("news_symbols_fetched"),
                "venue_provider": diagnostics.get("venue_provider"),
                "venue_quote_status": diagnostics.get("venue_quote_status"),
                "venue_quote_count": diagnostics.get("venue_quote_count"),
                "venue_product_count": diagnostics.get("venue_product_count"),
                "venue_orderbook_count": diagnostics.get("venue_orderbook_count"),
                "venue_spread_eligible_count": diagnostics.get("venue_spread_eligible_count"),
                "venue_depth_eligible_count": diagnostics.get("venue_depth_eligible_count"),
                "venue_gate_applied": diagnostics.get("venue_gate_applied"),
                "asset_discovery_error": diagnostics.get("asset_discovery_error"),
                "cache_created_at": diagnostics.get("cache_created_at"),
            }
        )
        st.caption("Score diagnostics help calibrate thresholds after enough mock results exist.")
        st.write(
            {
                "candidate_count": score_report["candidate_count"],
                "valid_count": score_report["valid_count"],
                "score_min": score_report["score_min"],
                "score_median": score_report["score_median"],
                "score_max": score_report["score_max"],
                "score_buckets": score_report["score_buckets"],
                "top_veto_reasons": score_report["top_veto_reasons"],
            }
        )


def _switch_to_trade_card() -> None:
    try:
        st.switch_page("app/pages/2_trade_card.py")
    except StreamlitAPIException:
        st.switch_page("pages/2_trade_card.py")


def render_trade_card(card: Mapping[str, object] | None) -> None:
    if not card:
        st.subheader("No Trade Tonight")
        st.caption("No candidate cleared the hard veto logic.")
        return

    if card.get("verdict") != "Valid Trade":
        st.subheader("No Trade Tonight")
        reasons = card.get("veto_reasons") or ["No candidate cleared the hard veto logic."]
        st.caption("Best candidate failed one or more hard rules.")
        st.write("\n".join(f"- {reason}" for reason in reasons))
        render_alpaca_depth_proxy_check(card)
        render_venue_check(card)
        render_execution_plan(card)
        return

    st.subheader(f"{card['ticker']} | {card['verdict']}")
    if card.get("data_confidence"):
        st.caption(f"{card.get('data_confidence')} | {card.get('limitations', '')}")
    left, middle, right = st.columns(3)
    left.metric("Score", f"{float(card['score']):.2f}")
    middle.metric("Phase", str(card["phase"]))
    right.metric("Risk/Reward", f"1:{float(card['risk_reward']):.2f}")

    st.write(card.get("reason_summary", ""))
    st.caption(card.get("catalyst_summary", ""))
    render_alpaca_depth_proxy_check(card)
    render_venue_check(card)
    render_execution_plan(card)

    breakdown = pd.DataFrame([card.get("score_breakdown", {})]).T.rename(columns={0: "Subscore"})
    st.bar_chart(breakdown)


def render_execution_plan(card: Mapping[str, object]) -> None:
    st.subheader("Execution Plan")
    levels = {
        "Profile": card.get("execution_profile"),
        "Quality": card.get("execution_quality"),
        "Entry": card.get("entry"),
        "Stop": card.get("stop"),
        "Stop Distance %": card.get("stop_distance_pct"),
        "Stop Basis": card.get("stop_basis"),
        "Target 1": card.get("target_1"),
        "T1 R": card.get("target_1_r"),
        "Target 2": card.get("target_2"),
        "T2 R": card.get("target_2_r"),
        "Momentum Life": card.get("estimated_momentum_life"),
    }
    st.dataframe(pd.DataFrame([levels]), width="stretch", hide_index=True)


def render_alpaca_depth_proxy_check(card: Mapping[str, object]) -> None:
    st.subheader("Alpaca Depth Proxy Check")
    values = {
        "Depth OK": "Yes" if card.get("alpaca_depth_proxy_ok") else "No",
        "Depth Notional": card.get("alpaca_depth_notional"),
        "Bid Depth": card.get("alpaca_depth_bid_notional"),
        "Ask Depth": card.get("alpaca_depth_ask_notional"),
        "BPS Window": card.get("alpaca_depth_bps"),
    }
    st.dataframe(pd.DataFrame([values]), width="stretch", hide_index=True)


def render_venue_check(card: Mapping[str, object]) -> None:
    st.subheader("Kraken Venue Check")
    quote_age = card.get("venue_quote_age_seconds")
    age_display = "" if quote_age in (None, "") else f"{float(quote_age):.1f}s"
    values = {
        "Status": card.get("venue_quote_status", ""),
        "Tradable": "Yes" if card.get("venue_tradable") else "No",
        "Symbol": card.get("venue_symbol"),
        "Bid": card.get("venue_bid"),
        "Ask": card.get("venue_ask"),
        "Mid": card.get("venue_mid"),
        "Spread %": card.get("venue_spread_pct"),
        "Depth Notional": card.get("venue_depth_notional"),
        "Quote Age": age_display,
        "Alpaca/Kraken Deviation %": card.get("alpaca_venue_price_deviation_pct"),
    }
    st.dataframe(pd.DataFrame([values]), width="stretch", hide_index=True)


def render_setup_instructions(settings: AppSettings) -> None:
    if settings.live_data_enabled:
        return
    st.warning("Connect Alpaca credentials before running a real-data scan.")
    st.code(
        """PROVIDER_MODE=live
ALPACA_API_KEY=your_key
ALPACA_SECRET_KEY=your_secret
MARKET_MODE=crypto
CRYPTO_LOCATION=us
CRYPTO_UNIVERSE_MODE=dynamic_safe_fallback
CRYPTO_SYMBOLS=BTC/USD,ETH/USD,SOL/USD,AVAX/USD,LINK/USD,UNI/USD,AAVE/USD,DOGE/USD,LTC/USD,BCH/USD
CRYPTO_SCAN_MINUTES=90
CRYPTO_MIN_QUOTE_VOLUME=50000
CRYPTO_MAX_SPREAD_PCT=0.35
CRYPTO_MIN_ORDERBOOK_NOTIONAL_DEPTH=25000
CRYPTO_DEPTH_BPS=25

VENUE_PROVIDER=kraken
KRAKEN_BASE_URL=https://api.kraken.com
KRAKEN_MAX_SPREAD_PCT=0.35
KRAKEN_MAX_QUOTE_AGE_SECONDS=30
KRAKEN_MIN_ORDERBOOK_NOTIONAL_DEPTH=25000
MAX_ALPACA_VENUE_DEVIATION_PCT=0.50

MOCK_STARTING_CASH=10000
MOCK_FEE_BPS=40
MOCK_SLIPPAGE_BPS=5
CALIBRATION_MIN_TRADES=30
CALIBRATION_HOLDOUT_PCT=30

TURSO_DATABASE_URL=your_turso_url
TURSO_AUTH_TOKEN=your_turso_token""",
        language="toml",
    )


def render_basic_data_banner(settings: AppSettings) -> None:
    st.warning(
        "Alpaca provides momentum bars and an early depth proxy; Kraken public data is the execution-venue quote gate. "
        "A setup is invalid unless Kraken confirms tradability, spread, and depth."
    )


def render_upgrade_trigger_note() -> None:
    with st.expander("Crypto data limitation"):
        st.write(
            "- Alpaca crypto data is venue-specific, not a global consolidated crypto tape.\n"
            "- Alpaca orderbook depth is an early proxy; Kraken orderbook depth is the final venue-depth gate.\n"
            "- Kraken public quotes can still differ from the exact fill you receive because fees, slippage, and order type matter.\n"
            "- Mock results are useful for workflow and strategy research, not proof of exchange-wide edge.\n"
            "- Before real-money sizing, compare candidate price, spread, and liquidity against the venue where you will execute."
        )


def render_manual_confirmation_checklist() -> None:
    st.subheader("Manual Confirmation")
    st.write(
        "- Confirm price and volume on your execution venue.\n"
        "- Confirm spread and liquidity are acceptable.\n"
        "- Confirm the structure is still clean and not a stale spike.\n"
        "- Confirm stop and targets still make sense before any real-money execution."
    )
