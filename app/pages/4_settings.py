from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from app.ui_helpers import effective_settings, page_setup
from src.storage.repositories import save_settings_version


page_setup("Settings")

st.title("Settings")
settings = effective_settings()

with st.form("settings"):
    st.subheader("Thresholds")
    min_score = st.slider("Minimum valid score", 0.0, 10.0, float(settings.min_score), 0.1)
    alert_score = st.slider("Alert score", 0.0, 10.0, float(settings.alert_score), 0.1)
    shortlist_size = st.slider("Shortlist size", 10, 30, int(settings.shortlist_size), 1)
    max_stop_distance_pct = st.slider("Max stop distance %", 1.0, 8.0, float(settings.max_stop_distance_pct), 0.1)
    min_risk_reward = st.slider("Minimum risk/reward", 1.0, 4.0, float(settings.min_risk_reward), 0.1)
    max_vwap_extension_pct = st.slider("Max VWAP extension %", 2.0, 15.0, float(settings.max_vwap_extension_pct), 0.1)
    mock_starting_cash = st.number_input("Mock starting cash", min_value=1000.0, value=float(settings.mock_starting_cash), step=1000.0)

    st.subheader("Weights")
    cols = st.columns(5)
    weight_rvol = cols[0].number_input("RVOL", value=float(settings.score_weights.rvol), step=0.01)
    weight_acceleration = cols[1].number_input("Acceleration", value=float(settings.score_weights.acceleration), step=0.01)
    weight_breakout = cols[2].number_input("Breakout", value=float(settings.score_weights.breakout_strength), step=0.01)
    weight_catalyst = cols[3].number_input("Catalyst", value=float(settings.score_weights.catalyst), step=0.01)
    weight_reversal_risk = cols[4].number_input("Reversal risk", value=float(settings.score_weights.reversal_risk), step=0.01)

    st.subheader("Provider")
    st.caption("Night Hunter v1 is real-data only and uses Alpaca Free/IEX batched REST plus shortlist-only streams.")
    submitted = st.form_submit_button("Apply Settings", type="primary")

if submitted:
    payload = {
        "min_score": min_score,
        "alert_score": alert_score,
        "shortlist_size": shortlist_size,
        "max_stop_distance_pct": max_stop_distance_pct,
        "min_risk_reward": min_risk_reward,
        "max_vwap_extension_pct": max_vwap_extension_pct,
        "mock_starting_cash": mock_starting_cash,
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
        "Alpaca feed": settings.alpaca_feed,
        "Credentials loaded": bool(settings.alpaca_api_key and settings.alpaca_secret_key),
        "Turso configured": bool(settings.turso_database_url and settings.turso_auth_token),
        "Database": str(settings.db_path),
    }
)
