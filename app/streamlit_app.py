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
    provider_label,
    render_basic_data_banner,
    render_scan_diagnostics,
    render_setup_instructions,
    render_shortlist_trade_card_launcher,
    render_trade_card,
    render_upgrade_trigger_note,
    scan_dataframe,
    universe_detail,
    universe_label,
    venue_label,
)
from src.jobs.run_scan import run_scan
from src.mock_trading.performance import compute_performance
from src.mock_trading.simulator import update_open_mock_trades
from src.providers.alpaca_provider import AlpacaProvider
from src.storage.db import init_db, storage_warning
from src.storage.repositories import latest_scan_results, latest_trade_card, list_mock_fills, list_mock_trades, portfolio_state


page_setup("Dashboard")
init_db()

st.title("Night Hunter")
st.caption("24/7 crypto momentum dashboard. Decision support and mock trading only; no real orders are placed.")

settings = effective_settings()
render_basic_data_banner(settings)
render_upgrade_trigger_note()
if storage_warning():
    st.warning(storage_warning())
result = st.session_state.get("latest_scan_result")
diagnostics = result.get("diagnostics", {}) if isinstance(result, dict) else {}
top = st.columns([1.2, 1, 1.4, 2])
top[0].metric("Data Feed", provider_label(settings))
top[1].metric("Venue Gate", venue_label(settings))
top[2].metric("Universe Source", universe_label(settings, diagnostics))
if universe_detail(diagnostics):
    top[2].caption(universe_detail(diagnostics))

render_setup_instructions(settings)

if settings.live_data_enabled and not st.session_state.get("mock_results_auto_refreshed"):
    try:
        update_open_mock_trades(AlpacaProvider(settings))
        st.session_state["mock_results_auto_refreshed"] = True
    except Exception as exc:
        st.caption(f"Mock result refresh skipped: {exc}")

if top[3].button("Run Crypto Scan", type="primary", width="stretch", disabled=not settings.live_data_enabled):
    with st.spinner("Running a rolling crypto scan and refreshing the shortlist..."):
        try:
            result = run_scan(settings=settings)
        except Exception as exc:
            st.error(f"Scan failed: {exc}")
        else:
            st.session_state["latest_scan_result"] = result
            if result["rows"]:
                st.success("Scan complete.")
            elif result.get("diagnostics", {}).get("universe_size", 0) and not result.get("diagnostics", {}).get(
                "symbols_with_1min_bars", 0
            ):
                st.warning("Scan complete, but no 1-minute crypto bars were found for the rolling window.")
            else:
                st.warning("Scan complete, but no candidates made it through universe/data availability filters.")

result = st.session_state.get("latest_scan_result")
rows = result["rows"] if result else latest_scan_results(settings.shortlist_size)
card = result["trade_card"] if result else latest_trade_card()
if result:
    diagnostics = result.get("diagnostics", {})
    st.caption(
        f"Active scan window ended {diagnostics.get('scan_window_end', 'unknown')} "
        f"({diagnostics.get('scan_window_label', 'rolling crypto window')})."
    )
else:
    st.caption(f"Crypto scans use the latest rolling {settings.crypto_scan_minutes}-minute window.")

render_trade_card(card)

st.divider()
st.subheader("Current Shortlist")
if result and not rows:
    diagnostics = result.get("diagnostics", {})
    if diagnostics.get("universe_size", 0) and not diagnostics.get("symbols_with_1min_bars", 0):
        st.warning("No 1-minute crypto bars found for the rolling window.")
    else:
        st.warning("No candidates made it through universe/data availability filters.")
st.dataframe(scan_dataframe(rows), width="stretch", hide_index=True)
render_shortlist_trade_card_launcher(rows, "dashboard")
render_scan_diagnostics(result)

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
