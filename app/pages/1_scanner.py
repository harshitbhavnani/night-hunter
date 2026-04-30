from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from app.ui_helpers import (
    effective_settings,
    page_setup,
    render_basic_data_banner,
    render_scan_diagnostics,
    render_setup_instructions,
    render_shortlist_trade_card_launcher,
    scan_dataframe,
    universe_detail,
    universe_label,
)
from src.jobs.run_scan import run_scan
from src.storage.repositories import latest_scan_results


page_setup("Scanner")

st.title("Scanner")
settings = effective_settings()
render_basic_data_banner(settings)
render_setup_instructions(settings)

left, middle, right = st.columns([1, 1, 2])
with left:
    run_now = st.button("Refresh Crypto Scan", type="primary", width="stretch", disabled=not settings.live_data_enabled)
    st.caption(f"Rolling {settings.crypto_scan_minutes}-minute scan over {universe_label(settings)}.")
with middle:
    refresh_universe = st.button(
        "Refresh Pair Cache",
        width="stretch",
        disabled=not settings.live_data_enabled,
    )
    st.caption("Rebuilds pair discovery and quote-volume cache.")
with right:
    st.info(
        "Ranking emphasizes abnormal volume, acceleration, breakout strength, low reversal risk, and tradable spread."
    )

if run_now or refresh_universe:
    with st.spinner("Scanning Alpaca crypto pairs..."):
        try:
            result = run_scan(settings=settings, force_refresh_universe=refresh_universe)
        except Exception as exc:
            st.error(f"Scan failed: {exc}")
        else:
            st.session_state["latest_scan_result"] = result
            if not result["rows"]:
                diagnostics = result.get("diagnostics", {})
                if diagnostics.get("universe_size", 0) and not diagnostics.get("symbols_with_1min_bars", 0):
                    st.warning("No 1-minute crypto bars found for the rolling window.")
                else:
                    st.warning("No candidates made it through universe/data availability filters.")

result = st.session_state.get("latest_scan_result")
rows = result["rows"] if result else latest_scan_results(settings.shortlist_size)
if result:
    diagnostics = result.get("diagnostics", {})
    st.caption(
        f"Active scan window ended {diagnostics.get('scan_window_end', 'unknown')} "
        f"({diagnostics.get('scan_window_label', 'rolling crypto window')})."
    )
    detail = universe_detail(diagnostics)
    st.caption(f"Universe source: {universe_label(settings, diagnostics)}" + (f" | {detail}" if detail else ""))
else:
    st.caption(f"Crypto scans use the latest rolling {settings.crypto_scan_minutes}-minute window.")

st.dataframe(
    scan_dataframe(rows),
    width="stretch",
    hide_index=True,
    column_config={
        "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=10, format="%.2f"),
    },
)

if rows:
    st.caption(f"{len(rows)} shortlisted symbols from the current universe.")
    render_shortlist_trade_card_launcher(rows, "scanner")
else:
    if result:
        diagnostics = result.get("diagnostics", {})
        if diagnostics.get("universe_size", 0) and not diagnostics.get("symbols_with_1min_bars", 0):
            st.warning("No 1-minute crypto bars found for the rolling window.")
        else:
            st.warning("No candidates made it through universe/data availability filters.")
    else:
        st.warning("No scan results yet. Connect Alpaca credentials and run a scan.")

render_scan_diagnostics(result)
