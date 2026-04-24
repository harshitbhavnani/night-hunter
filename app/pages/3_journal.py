from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from app.ui_helpers import page_setup
from src.storage.repositories import add_journal_entry, latest_trade_card, list_journal_entries


page_setup("Journal")

st.title("Journal")

card = latest_trade_card() or {}
with st.form("journal_entry"):
    left, right = st.columns(2)
    trade_date = left.date_input("Date", value=date.today())
    ticker = left.text_input("Ticker", value=str(card.get("ticker", "")))
    phase = left.text_input("Phase", value=str(card.get("phase", "")))
    score = left.number_input("Score", value=float(card.get("score", 0) or 0), min_value=0.0, max_value=10.0)
    catalyst = right.text_area("Catalyst", value=str(card.get("catalyst_summary", "")), height=80)
    entry = right.number_input("Entry", value=float(card.get("entry", 0) or 0), min_value=0.0)
    stop = right.number_input("Stop", value=float(card.get("stop", 0) or 0), min_value=0.0)
    target_1 = right.number_input("Target 1", value=float(card.get("target_1", 0) or 0), min_value=0.0)
    target_2 = right.number_input("Target 2", value=float(card.get("target_2", 0) or 0), min_value=0.0)
    exit_price = st.number_input("Exit", value=0.0, min_value=0.0)
    pnl = st.number_input("P/L", value=0.0)
    notes = st.text_area("Notes")
    submitted = st.form_submit_button("Save Journal Entry", type="primary")

if submitted:
    add_journal_entry(
        {
            "trade_date": trade_date.isoformat(),
            "ticker": ticker,
            "phase": phase,
            "score": score,
            "catalyst": catalyst,
            "entry": entry,
            "stop": stop,
            "target_1": target_1,
            "target_2": target_2,
            "exit": exit_price if exit_price else None,
            "pnl": pnl,
            "notes": notes,
        }
    )
    st.success("Journal entry saved.")

entries = list_journal_entries()
st.subheader("History")
if entries:
    st.dataframe(pd.DataFrame(entries), use_container_width=True, hide_index=True)
else:
    st.caption("No journal entries yet.")

