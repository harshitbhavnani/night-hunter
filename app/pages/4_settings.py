from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from app.ui_helpers import effective_settings, page_setup, render_basic_data_banner, render_upgrade_trigger_note
from src.storage.repositories import save_settings_version


page_setup("Settings")

st.title("Settings")
settings = effective_settings()
render_basic_data_banner(settings)
render_upgrade_trigger_note()

with st.form("settings"):
    st.subheader("Thresholds")
    st.caption("These thresholds decide whether a scanned candidate is a valid trade. They do not control initial universe discovery.")
    min_score = st.slider("Minimum valid score", 0.0, 10.0, float(settings.min_score), 0.1)
    shortlist_size = st.slider("Shortlist size", 10, 30, int(settings.shortlist_size), 1)
    max_stop_distance_pct = st.slider("Max stop distance %", 1.0, 8.0, float(settings.max_stop_distance_pct), 0.1)
    min_risk_reward = st.slider("Minimum risk/reward", 1.0, 4.0, float(settings.min_risk_reward), 0.1)
    max_vwap_extension_pct = st.slider("Max VWAP extension %", 2.0, 15.0, float(settings.max_vwap_extension_pct), 0.1)

    st.subheader("Mock Trading")
    st.caption("Mock exits include estimated venue fees and slippage so performance is not over-clean.")
    mock_cols = st.columns(3)
    mock_starting_cash = mock_cols[0].number_input(
        "Mock starting cash",
        min_value=1000.0,
        value=float(settings.mock_starting_cash),
        step=1000.0,
    )
    mock_fee_bps = mock_cols[1].number_input(
        "Fee bps per side",
        min_value=0.0,
        max_value=300.0,
        value=float(settings.mock_fee_bps),
        step=1.0,
        help="Applied on entry notional and exit notional when mock fills are replayed.",
    )
    mock_slippage_bps = mock_cols[2].number_input(
        "Exit slippage bps",
        min_value=0.0,
        max_value=200.0,
        value=float(settings.mock_slippage_bps),
        step=1.0,
        help="Conservative markdown applied to simulated long exits.",
    )

    st.subheader("Calibration")
    st.caption("Calibration is advisory only. It analyzes closed mock trades and does not auto-change settings.")
    calibration_cols = st.columns(2)
    calibration_min_trades = calibration_cols[0].number_input(
        "Minimum closed trades",
        min_value=10,
        max_value=500,
        value=int(settings.calibration_min_trades),
        step=5,
    )
    calibration_holdout_pct = calibration_cols[1].number_input(
        "Holdout %",
        min_value=10.0,
        max_value=60.0,
        value=float(settings.calibration_holdout_pct),
        step=5.0,
    )

    st.subheader("Weights")
    st.caption("Crypto mode defaults catalyst weight to 0 because setups are structure-first.")
    cols = st.columns(5)
    weight_rvol = cols[0].number_input("RVOL", value=float(settings.score_weights.rvol), step=0.01)
    weight_acceleration = cols[1].number_input("Acceleration", value=float(settings.score_weights.acceleration), step=0.01)
    weight_breakout = cols[2].number_input("Breakout", value=float(settings.score_weights.breakout_strength), step=0.01)
    weight_catalyst = cols[3].number_input("Catalyst", value=float(settings.score_weights.catalyst), step=0.01)
    weight_reversal_risk = cols[4].number_input("Reversal risk", value=float(settings.score_weights.reversal_risk), step=0.01)

    st.subheader("Crypto Universe")
    st.caption(
        "Dynamic mode discovers active tradable Alpaca USD crypto pairs. The list below is only the safe fallback."
    )
    crypto_universe_mode = st.selectbox(
        "Universe mode",
        ["dynamic_safe_fallback", "fixed"],
        index=0 if settings.crypto_universe_mode == "dynamic_safe_fallback" else 1,
        help="dynamic_safe_fallback discovers all Alpaca USD crypto pairs and uses the safe list only if discovery fails.",
    )
    crypto_symbols = st.text_area(
        "Safe fallback pairs",
        value=",".join(settings.crypto_symbols),
        height=80,
        help="Comma-separated fallback symbols such as BTC/USD,ETH/USD,SOL/USD. Fixed mode scans only these pairs.",
    )
    universe_cols = st.columns(4)
    crypto_location = universe_cols[0].selectbox(
        "Location",
        ["us", "global"],
        index=0 if settings.crypto_location == "us" else 1,
    )
    crypto_scan_minutes = universe_cols[1].number_input(
        "Rolling scan minutes",
        min_value=15,
        max_value=360,
        value=int(settings.crypto_scan_minutes),
        step=15,
    )
    crypto_min_quote_volume = universe_cols[2].number_input(
        "Min daily Alpaca quote volume",
        min_value=0.0,
        value=float(settings.crypto_min_quote_volume),
        step=10_000.0,
        help="Daily Alpaca-venue quote-volume discovery floor. The rolling scan uses a time-window-scaled version of this value.",
    )
    crypto_max_spread_pct = universe_cols[3].number_input(
        "Max spread %",
        min_value=0.01,
        max_value=5.0,
        value=float(settings.crypto_max_spread_pct),
        step=0.05,
    )
    depth_cols = st.columns(2)
    crypto_min_orderbook_notional_depth = depth_cols[0].number_input(
        "Min Alpaca depth proxy $",
        min_value=0.0,
        value=float(settings.crypto_min_orderbook_notional_depth),
        step=5_000.0,
        help="Minimum Alpaca bid/ask notional depth inside the configured BPS window. This is an early proxy, not the final venue gate.",
    )
    crypto_depth_bps = depth_cols[1].number_input(
        "Depth BPS window",
        min_value=1.0,
        max_value=200.0,
        value=float(settings.crypto_depth_bps),
        step=1.0,
    )

    st.subheader("Kraken Venue Gate")
    st.caption("Kraken public market data is the execution venue check. Orders are still disabled; this only validates quotes and depth.")
    venue_provider = st.selectbox("Venue provider", ["kraken"], index=0)
    kraken_base_url = st.text_input("Kraken base URL", value=settings.kraken_base_url)
    venue_cols = st.columns(4)
    kraken_max_spread_pct = venue_cols[0].number_input(
        "Kraken max spread %",
        min_value=0.01,
        max_value=5.0,
        value=float(settings.kraken_max_spread_pct),
        step=0.05,
    )
    kraken_max_quote_age_seconds = venue_cols[1].number_input(
        "Max quote age seconds",
        min_value=1,
        max_value=120,
        value=int(settings.kraken_max_quote_age_seconds),
        step=1,
    )
    max_alpaca_venue_deviation_pct = venue_cols[2].number_input(
        "Max Alpaca/Kraken deviation %",
        min_value=0.01,
        max_value=5.0,
        value=float(settings.max_alpaca_venue_deviation_pct),
        step=0.05,
    )
    kraken_min_orderbook_notional_depth = venue_cols[3].number_input(
        "Min Kraken depth $",
        min_value=0.0,
        value=float(settings.kraken_min_orderbook_notional_depth),
        step=5_000.0,
    )

    st.subheader("Provider")
    st.caption("Night Hunter uses Alpaca for historical bars and Kraken for public venue quote/depth validation.")
    submitted = st.form_submit_button("Apply Settings", type="primary")

if submitted:
    payload = {
        "min_score": min_score,
        "shortlist_size": shortlist_size,
        "max_stop_distance_pct": max_stop_distance_pct,
        "min_risk_reward": min_risk_reward,
        "max_vwap_extension_pct": max_vwap_extension_pct,
        "mock_starting_cash": mock_starting_cash,
        "mock_fee_bps": mock_fee_bps,
        "mock_slippage_bps": mock_slippage_bps,
        "calibration_min_trades": calibration_min_trades,
        "calibration_holdout_pct": calibration_holdout_pct,
        "crypto_universe_mode": crypto_universe_mode,
        "crypto_symbols": crypto_symbols,
        "crypto_location": crypto_location,
        "crypto_scan_minutes": crypto_scan_minutes,
        "crypto_min_quote_volume": crypto_min_quote_volume,
        "crypto_max_spread_pct": crypto_max_spread_pct,
        "crypto_min_orderbook_notional_depth": crypto_min_orderbook_notional_depth,
        "crypto_depth_bps": crypto_depth_bps,
        "venue_provider": venue_provider,
        "kraken_base_url": kraken_base_url,
        "kraken_max_spread_pct": kraken_max_spread_pct,
        "kraken_max_quote_age_seconds": kraken_max_quote_age_seconds,
        "kraken_min_orderbook_notional_depth": kraken_min_orderbook_notional_depth,
        "max_alpaca_venue_deviation_pct": max_alpaca_venue_deviation_pct,
        "weight_rvol": weight_rvol,
        "weight_acceleration": weight_acceleration,
        "weight_breakout": weight_breakout,
        "weight_catalyst": weight_catalyst,
        "weight_reversal_risk": weight_reversal_risk,
    }
    st.session_state["night_hunter_settings"] = payload
    save_settings_version(payload)
    st.success("Settings applied for this Streamlit session and versioned in SQLite.")

st.divider()
st.subheader("Environment")
st.write(
    {
        "Market mode": "crypto",
        "Universe mode": settings.crypto_universe_mode,
        "Crypto location": settings.crypto_location,
        "Safe fallback pairs": ", ".join(settings.crypto_symbols),
        "Credentials loaded": bool(settings.alpaca_api_key and settings.alpaca_secret_key),
        "Venue provider": settings.venue_provider,
        "Kraken public data": settings.venue_quote_gate_ready,
        "Kraken base URL": settings.kraken_base_url,
        "Turso configured": bool(settings.turso_database_url and settings.turso_auth_token),
        "Database": str(settings.db_path),
        "Data confidence": "Alpaca Crypto",
        "Mock fee bps": settings.mock_fee_bps,
        "Mock slippage bps": settings.mock_slippage_bps,
        "Calibration min trades": settings.calibration_min_trades,
        "Calibration holdout %": settings.calibration_holdout_pct,
        "Rolling scan minutes": settings.crypto_scan_minutes,
        "Min quote volume": settings.crypto_min_quote_volume,
        "Max spread %": settings.crypto_max_spread_pct,
        "Min Alpaca depth proxy $": settings.crypto_min_orderbook_notional_depth,
        "Depth BPS window": settings.crypto_depth_bps,
        "Kraken max spread %": settings.kraken_max_spread_pct,
        "Kraken max quote age seconds": settings.kraken_max_quote_age_seconds,
        "Kraken min depth $": settings.kraken_min_orderbook_notional_depth,
        "Max Alpaca/Kraken deviation %": settings.max_alpaca_venue_deviation_pct,
    }
)
