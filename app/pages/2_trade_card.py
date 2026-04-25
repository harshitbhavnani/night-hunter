from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from app.ui_helpers import (
    effective_settings,
    page_setup,
    render_basic_data_banner,
    render_manual_confirmation_checklist,
    render_setup_instructions,
    render_trade_card,
    render_upgrade_trigger_note,
)
from src.jobs.run_scan import run_scan
from src.mock_trading.entry import enter_mock_trade
from src.mock_trading.recommendations import recommend_entry_controls
from src.mock_trading.simulator import update_open_mock_trades
from src.providers.alpaca_provider import AlpacaProvider
from src.storage.repositories import latest_trade_card, portfolio_state
from src.utils.timeframes import utc_window


page_setup("Trade Card")

st.title("Trade Card")
settings = effective_settings()
render_basic_data_banner(settings)
render_upgrade_trigger_note()
render_setup_instructions(settings)

if st.button("Generate Current Trade Card", type="primary", disabled=not settings.live_data_enabled):
    with st.spinner("Checking hard veto rules and execution levels..."):
        try:
            st.session_state["latest_scan_result"] = run_scan(settings=settings)
        except Exception as exc:
            st.error(f"Scan failed: {exc}")

if st.button("Update Mock Results", disabled=not settings.live_data_enabled):
    with st.spinner("Replaying open mock trades with Alpaca bars..."):
        try:
            updates = update_open_mock_trades(AlpacaProvider(settings))
        except Exception as exc:
            st.error(f"Mock update failed: {exc}")
        else:
            st.success(f"Updated {len(updates)} open mock trade(s).")

result = st.session_state.get("latest_scan_result")
card = result["trade_card"] if result else latest_trade_card()

render_trade_card(card)
if card and card.get("verdict") == "Valid Trade":
    render_manual_confirmation_checklist()

if card and card.get("verdict") == "Valid Trade":
    st.divider()
    st.subheader("Enter Mock Trade")
    state = portfolio_state(settings.mock_starting_cash)
    recommendations = recommend_entry_controls(card, float(state["cash"]))
    with st.form("enter_mock_trade"):
        cols = st.columns(4)
        dollar_amount = cols[0].number_input(
            "Dollar amount",
            min_value=0.0,
            max_value=max(0.0, float(state["cash"])),
            value=float(recommendations["dollar_amount"]),
            step=50.0,
        )
        max_hold_minutes = cols[1].number_input(
            "Max hold minutes",
            min_value=1,
            max_value=240,
            value=int(recommendations["max_hold_minutes"]),
            step=1,
        )
        target_1_pct = cols[2].number_input(
            "Target 1 %",
            min_value=1,
            max_value=99,
            value=int(recommendations["target_1_pct"]),
            step=1,
        )
        target_2_pct = cols[3].number_input(
            "Target 2 %",
            min_value=1,
            max_value=99,
            value=int(100 - target_1_pct),
            step=1,
        )
        level_cols = st.columns(4)
        entry = level_cols[0].number_input("Entry", min_value=0.0, value=float(card.get("entry", 0)), step=0.01)
        stop = level_cols[1].number_input("Stop", min_value=0.0, value=float(card.get("stop", 0)), step=0.01)
        target_1 = level_cols[2].number_input("Target 1", min_value=0.0, value=float(card.get("target_1", 0)), step=0.01)
        target_2 = level_cols[3].number_input("Target 2", min_value=0.0, value=float(card.get("target_2", 0)), step=0.01)
        notes = st.text_area("Notes", height=80)
        st.caption(
            f"Recommended allocation: {recommendations['allocation_pct']:.1f}% of available cash. "
            "After Target 1, remaining stop moves to breakeven."
        )
        submitted = st.form_submit_button("Enter Mock Trade", type="primary")
    if submitted:
        try:
            trade_id = enter_mock_trade(
                card,
                dollar_amount=dollar_amount,
                max_hold_minutes=int(max_hold_minutes),
                target_1_pct=float(target_1_pct),
                target_2_pct=float(target_2_pct),
                entry=entry,
                stop=stop,
                target_1=target_1,
                target_2=target_2,
                notes=notes,
            )
        except Exception as exc:
            st.error(f"Could not enter mock trade: {exc}")
        else:
            st.success(f"Mock trade #{trade_id} entered.")

if card and card.get("ticker") and settings.live_data_enabled:
    st.divider()
    st.subheader("Compact Chart")
    provider = AlpacaProvider(settings)
    start, end = utc_window(90)
    bars = provider.get_historical_bars([str(card["ticker"])], "1Min", start, end).get(str(card["ticker"]), [])
    if bars:
        chart_frame = pd.DataFrame(bars)
        chart_frame["t"] = pd.to_datetime(chart_frame["t"])
        chart_frame = chart_frame.set_index("t")
        st.line_chart(chart_frame[["c"]].rename(columns={"c": "Close"}), height=260)
        levels = pd.DataFrame(
            {
                "Level": ["Entry", "Stop", "Target 1", "Target 2"],
                "Price": [card.get("entry"), card.get("stop"), card.get("target_1"), card.get("target_2")],
            }
        )
        st.dataframe(levels, use_container_width=True, hide_index=True)
    else:
        st.caption(f"No recent bars available as of {datetime.now(timezone.utc).isoformat()}.")
