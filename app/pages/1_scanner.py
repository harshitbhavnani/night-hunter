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
    run_now = st.button("Refresh Scan", type="primary", use_container_width=True, disabled=not settings.live_data_enabled)
    st.caption(f"Stage 1 uses batched REST. Stage 2 streams only the top {settings.shortlist_size} symbols.")
with middle:
    refresh_universe = st.button(
        "Refresh Universe Cache",
        use_container_width=True,
        disabled=not settings.live_data_enabled,
    )
    st.caption("Rebuilds Alpaca assets and daily IEX ADV cache.")
with right:
    st.info(
        "Ranking emphasizes abnormal volume, acceleration, breakout strength, catalyst presence, and low reversal risk."
    )

if run_now or refresh_universe:
    with st.spinner("Scanning the Alpaca Free-compatible universe..."):
        try:
            result = run_scan(settings=settings, force_refresh_universe=refresh_universe)
        except Exception as exc:
            st.error(f"Scan failed: {exc}")
        else:
            st.session_state["latest_scan_result"] = result
            if not result["rows"]:
                st.warning("No candidates made it through universe/data availability filters.")

result = st.session_state.get("latest_scan_result")
rows = result["rows"] if result else latest_scan_results(settings.shortlist_size)

st.dataframe(
    scan_dataframe(rows),
    use_container_width=True,
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
        st.warning("No candidates made it through universe/data availability filters.")
    else:
        st.warning("No scan results yet. Connect Alpaca credentials and run a scan.")

render_scan_diagnostics(result)
