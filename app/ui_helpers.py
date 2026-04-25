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

from src.config import AppSettings, ScoreWeights, get_settings


TABLE_COLUMNS = {
    "ticker": "Ticker",
    "price": "Price",
    "avg_daily_volume": "IEX ADV",
    "day_change_pct": "% Day",
    "return_15m": "% 15m",
    "rvol": "RVOL",
    "acceleration": "Acceleration",
    "phase": "Phase",
    "has_catalyst": "Catalyst",
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
        alert_score=float(payload.get("alert_score", base.alert_score)),
        shortlist_size=int(payload.get("shortlist_size", base.shortlist_size)),
        max_stop_distance_pct=float(payload.get("max_stop_distance_pct", base.max_stop_distance_pct)),
        min_risk_reward=float(payload.get("min_risk_reward", base.min_risk_reward)),
        max_vwap_extension_pct=float(payload.get("max_vwap_extension_pct", base.max_vwap_extension_pct)),
        mock_starting_cash=float(payload.get("mock_starting_cash", base.mock_starting_cash)),
        basic_min_iex_avg_daily_volume=float(
            payload.get("basic_min_iex_avg_daily_volume", base.basic_min_iex_avg_daily_volume)
        ),
        basic_max_universe_symbols=int(payload.get("basic_max_universe_symbols", base.basic_max_universe_symbols)),
        score_weights=weights,
    )


def scan_dataframe(rows: list[Mapping[str, object]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=list(TABLE_COLUMNS.values()))
    frame = pd.DataFrame(rows)
    for column in TABLE_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    frame = frame[list(TABLE_COLUMNS.keys())].rename(columns=TABLE_COLUMNS)
    numeric = ["Price", "IEX ADV", "% Day", "% 15m", "RVOL", "Acceleration", "Score"]
    for column in numeric:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").round(2)
    frame["Catalyst"] = frame["Catalyst"].map(lambda value: "Yes" if value else "No")
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
    if right.button("Open Trade Card", key=f"{key_prefix}_open_trade_card", use_container_width=True):
        st.session_state["selected_trade_symbol"] = selected
        _switch_to_trade_card()


def render_scan_diagnostics(result: Mapping[str, object] | None) -> None:
    diagnostics = (result or {}).get("diagnostics")
    if not isinstance(diagnostics, Mapping):
        return

    with st.expander("Scan Diagnostics"):
        cache_source = diagnostics.get("cache_source", "unknown")
        cache_age = diagnostics.get("cache_age_minutes")
        cache_text = f"{cache_source}"
        if cache_age is not None:
            cache_text += f" ({float(cache_age):.1f} min old)"
        st.caption(f"Universe cache: {cache_text}")
        columns = st.columns(4)
        metrics = [
            ("Assets", diagnostics.get("assets_loaded")),
            ("Common Stocks", diagnostics.get("common_stock_count")),
            ("Price Eligible", diagnostics.get("price_eligible_count")),
            ("Volume Eligible", diagnostics.get("volume_eligible_count")),
            ("Universe", diagnostics.get("universe_size")),
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
                "volume_floor": diagnostics.get("volume_floor"),
                "max_universe_symbols": diagnostics.get("max_universe_symbols"),
                "news_symbols_fetched": diagnostics.get("news_symbols_fetched"),
                "cache_created_at": diagnostics.get("cache_created_at"),
            }
        )


def _switch_to_trade_card() -> None:
    try:
        st.switch_page("app/pages/2_trade_card.py")
    except StreamlitAPIException:
        st.switch_page("pages/2_trade_card.py")


def render_trade_card(card: Mapping[str, object] | None) -> None:
    if not card or card.get("verdict") != "Valid Trade":
        st.subheader("No Trade Tonight")
        reasons = (card or {}).get("veto_reasons") or ["No candidate cleared the hard veto logic."]
        st.caption("Best candidate failed one or more hard rules.")
        st.write("\n".join(f"- {reason}" for reason in reasons))
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

    levels = {
        "Entry": card.get("entry"),
        "Stop": card.get("stop"),
        "Target 1": card.get("target_1"),
        "Target 2": card.get("target_2"),
        "Momentum Life": card.get("estimated_momentum_life"),
    }
    st.dataframe(pd.DataFrame([levels]), use_container_width=True, hide_index=True)

    breakdown = pd.DataFrame([card.get("score_breakdown", {})]).T.rename(columns={0: "Subscore"})
    st.bar_chart(breakdown)


def render_setup_instructions(settings: AppSettings) -> None:
    if settings.live_data_enabled:
        return
    st.warning("Connect Alpaca credentials before running a real-data scan.")
    st.code(
        """PROVIDER_MODE=live
ALPACA_API_KEY=your_key
ALPACA_SECRET_KEY=your_secret
ALPACA_FEED=iex

TURSO_DATABASE_URL=your_turso_url
TURSO_AUTH_TOKEN=your_turso_token""",
        language="toml",
    )


def render_basic_data_banner(settings: AppSettings) -> None:
    if settings.alpaca_feed.lower() != "iex":
        return
    st.warning(
        "Basic/IEX data only. Signals may miss consolidated market volume, quotes, and breakouts."
    )


def render_upgrade_trigger_note() -> None:
    with st.expander("When to upgrade data"):
        st.write(
            "- Upgrade to Alpaca Algo Trader Plus before relying on mock results for real-money scaling.\n"
            "- Upgrade if Night Hunter frequently disagrees with Robinhood Legend charts.\n"
            "- Upgrade if the strategy depends on fast breakouts, tight spreads, or full-market RVOL."
        )


def render_manual_confirmation_checklist() -> None:
    st.subheader("Manual Confirmation")
    st.write(
        "- Confirm price and volume in Robinhood Legend.\n"
        "- Confirm spread and liquidity are acceptable.\n"
        "- Confirm the catalyst is real and current.\n"
        "- Confirm stop and targets still make sense before any real-money execution."
    )
