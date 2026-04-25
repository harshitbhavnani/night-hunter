from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from app.ui_helpers import (
    effective_settings,
    page_setup,
    render_basic_data_banner,
    render_setup_instructions,
    render_shortlist_trade_card_launcher,
    render_trade_card,
    render_upgrade_trigger_note,
    scan_dataframe,
)
from src.jobs.run_scan import run_scan
from src.mock_trading.performance import compute_performance
from src.mock_trading.simulator import update_open_mock_trades
from src.providers.alpaca_provider import AlpacaProvider
from src.storage.db import init_db
from src.storage.repositories import latest_scan_results, latest_trade_card, list_mock_fills, list_mock_trades, portfolio_state


page_setup("Dashboard")
init_db()

st.title("Night Hunter")
st.caption("One trade per night momentum dashboard for U.S. equities. Decision support only; execution stays manual.")

settings = effective_settings()
render_basic_data_banner(settings)
render_upgrade_trigger_note()
top = st.columns([1, 1, 2])
top[0].metric("Provider", "Alpaca Free/IEX" if settings.live_data_enabled else "Not connected")
top[1].metric("Shortlist", settings.shortlist_size)

render_setup_instructions(settings)

if settings.live_data_enabled and not st.session_state.get("mock_results_auto_refreshed"):
    try:
        update_open_mock_trades(AlpacaProvider(settings))
        st.session_state["mock_results_auto_refreshed"] = True
    except Exception as exc:
        st.caption(f"Mock result refresh skipped: {exc}")

if top[2].button("Run Scan", type="primary", use_container_width=True, disabled=not settings.live_data_enabled):
    with st.spinner("Running batched Stage 1 scan and refreshing the shortlist..."):
        try:
            result = run_scan(settings=settings)
        except Exception as exc:
            st.error(f"Scan failed: {exc}")
        else:
            st.session_state["latest_scan_result"] = result
            st.success("Scan complete.")

result = st.session_state.get("latest_scan_result")
rows = result["rows"] if result else latest_scan_results(settings.shortlist_size)
card = result["trade_card"] if result else latest_trade_card()

render_trade_card(card)

st.divider()
st.subheader("Current Shortlist")
st.dataframe(scan_dataframe(rows), use_container_width=True, hide_index=True)
render_shortlist_trade_card_launcher(rows, "dashboard")

st.divider()
st.subheader("Mock Strategy Snapshot")
state = portfolio_state(settings.mock_starting_cash)
metrics = compute_performance(list_mock_trades(), list_mock_fills(), settings.mock_starting_cash)
cols = st.columns(5)
cols[0].metric("Equity", f"${state['equity']:,.2f}")
cols[1].metric("Cash", f"${state['cash']:,.2f}")
cols[2].metric("Total P/L", f"${metrics['total_pnl']:,.2f}")
cols[3].metric("Win Rate", f"{metrics['win_rate']:.1f}%")
cols[4].metric("Max DD", f"{metrics['max_drawdown']:.1f}%")
curve = pd.DataFrame(metrics["equity_curve"])
if len(curve) > 1:
    st.line_chart(curve.set_index("time")["equity"])
