from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from app.ui_helpers import effective_settings, page_setup, render_basic_data_banner
from src.mock_trading.history import build_trade_history_rows
from src.storage.repositories import list_mock_fills, list_mock_trades


page_setup("Trade History")

st.title("Trade History")
settings = effective_settings()
render_basic_data_banner(settings)

trades = list_mock_trades()
fills = list_mock_fills()
history_rows = build_trade_history_rows(trades, fills)

st.subheader("Mock Trades")
if history_rows:
    frame = pd.DataFrame(history_rows)
    visible = [
        "id",
        "entered_at",
        "ticker",
        "status",
        "phase",
        "score",
        "dollar_amount",
        "shares",
        "remaining_shares",
        "entry",
        "stop",
        "current_stop",
        "target_1",
        "target_2",
        "target_1_pct",
        "target_2_pct",
        "max_hold_minutes",
        "realized_pnl",
        "exit_reason",
        "closed_at",
        "feed",
        "data_confidence",
        "notes",
    ]
    st.dataframe(frame[[column for column in visible if column in frame.columns]], use_container_width=True, hide_index=True)

    with st.expander("Settings Snapshots"):
        settings_columns = [
            "id",
            "ticker",
            "settings_min_score",
            "settings_alert_score",
            "settings_shortlist_size",
            "settings_max_stop_distance_pct",
            "settings_min_risk_reward",
            "settings_max_vwap_extension_pct",
            "weight_rvol",
            "weight_acceleration",
            "weight_breakout",
            "weight_catalyst",
            "weight_reversal_risk",
            "feed",
            "data_confidence",
        ]
        st.dataframe(
            frame[[column for column in settings_columns if column in frame.columns]],
            use_container_width=True,
            hide_index=True,
        )
else:
    st.caption("No mock trades entered yet.")

st.subheader("Fills")
if fills:
    fill_frame = pd.DataFrame(fills)
    st.dataframe(fill_frame, use_container_width=True, hide_index=True)
else:
    st.caption("No fills yet.")
