from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from app.ui_helpers import effective_settings, page_setup, render_setup_instructions
from src.mock_trading.performance import compute_performance
from src.mock_trading.simulator import update_open_mock_trades
from src.providers.alpaca_provider import AlpacaProvider
from src.storage.repositories import list_mock_fills, list_mock_trades, portfolio_state


page_setup("Performance")

st.title("Mock Strategy Performance")
settings = effective_settings()
render_setup_instructions(settings)

if st.button("Update Mock Results", type="primary", disabled=not settings.live_data_enabled):
    with st.spinner("Replaying open trades with Alpaca 1-minute bars..."):
        try:
            updates = update_open_mock_trades(AlpacaProvider(settings))
        except Exception as exc:
            st.error(f"Mock update failed: {exc}")
        else:
            st.success(f"Updated {len(updates)} open mock trade(s).")

trades = list_mock_trades()
fills = list_mock_fills()
state = portfolio_state(settings.mock_starting_cash)
performance = compute_performance(trades, fills, settings.mock_starting_cash)

cols = st.columns(5)
cols[0].metric("Equity", f"${state['equity']:,.2f}")
cols[1].metric("Available Cash", f"${state['cash']:,.2f}")
cols[2].metric("Total P/L", f"${performance['total_pnl']:,.2f}")
cols[3].metric("Win Rate", f"{performance['win_rate']:.1f}%")
cols[4].metric("Avg R", f"{performance['average_r']:.2f}")

cols = st.columns(5)
cols[0].metric("Max Drawdown", f"{performance['max_drawdown']:.1f}%")
cols[1].metric("T1 Hit Rate", f"{performance['target_1_hit_rate']:.1f}%")
cols[2].metric("T2 Hit Rate", f"{performance['target_2_hit_rate']:.1f}%")
cols[3].metric("Avg Hold", f"{performance['average_hold_minutes']:.1f}m")
cols[4].metric("Open Trades", str(performance["open_trade_count"]))

curve = pd.DataFrame(performance["equity_curve"])
if len(curve) > 1:
    st.subheader("Equity Curve")
    st.line_chart(curve.set_index("time")["equity"], height=260)

st.subheader("Breakdowns")
left, middle, right = st.columns(3)
for column, title, payload in (
    (left, "By Phase", performance["pnl_by_phase"]),
    (middle, "By Score", performance["pnl_by_score_bucket"]),
    (right, "By Ticker", performance["pnl_by_ticker"]),
):
    frame = pd.DataFrame([payload]).T.rename(columns={0: "P/L"})
    column.dataframe(frame, use_container_width=True)

st.subheader("Trade Log")
if trades:
    trade_frame = pd.DataFrame(trades)
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
        "target_1",
        "target_2",
        "realized_pnl",
        "exit_reason",
        "closed_at",
        "notes",
    ]
    st.dataframe(trade_frame[[col for col in visible if col in trade_frame.columns]], use_container_width=True)
else:
    st.caption("No mock trades entered yet.")

st.subheader("Fills")
if fills:
    st.dataframe(pd.DataFrame(fills), use_container_width=True)
else:
    st.caption("No fills yet.")
