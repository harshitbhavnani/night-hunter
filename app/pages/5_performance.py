from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from app.ui_helpers import effective_settings, page_setup, render_basic_data_banner, render_setup_instructions
from src.analysis.calibration import build_calibration_report
from src.mock_trading.performance import compute_performance
from src.mock_trading.simulator import update_open_mock_trades
from src.providers.alpaca_provider import AlpacaProvider
from src.storage.repositories import list_mock_fills, list_mock_trades, portfolio_state


page_setup("Performance")

st.title("Mock Strategy Performance")
settings = effective_settings()
render_basic_data_banner(settings)
st.caption("Mock exits are replayed from Alpaca crypto 1-minute bars, not a consolidated global crypto tape.")
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

st.subheader("Calibration Advisor")
st.caption("Walk-forward review of closed mock trades. It never auto-applies settings.")
report = build_calibration_report(
    trades,
    min_trades=int(settings.calibration_min_trades),
    holdout_pct=float(settings.calibration_holdout_pct),
)
cal_cols = st.columns(4)
cal_cols[0].metric("Readiness", str(report["readiness"]).title())
cal_cols[1].metric("Closed Trades", str(report["closed_trades"]))
cal_cols[2].metric("Min Needed", str(report["min_trades"]))
cal_cols[3].metric("Holdout", f"{float(report['holdout_pct']):.0f}%")
st.info(str(report["message"]))
baseline = report.get("baseline", {})
if isinstance(baseline, dict):
    base_cols = st.columns(4)
    base_cols[0].metric("Baseline Expectancy", f"{float(baseline.get('expectancy_r', 0) or 0):.2f}R")
    base_cols[1].metric("Baseline Win Rate", f"{float(baseline.get('win_rate', 0) or 0):.1f}%")
    base_cols[2].metric("Avg Score", f"{float(baseline.get('average_score', 0) or 0):.2f}")
    base_cols[3].metric("Drawdown", f"{float(baseline.get('max_drawdown_r', 0) or 0):.2f}R")

recommendation = report.get("recommendation", {})
if isinstance(recommendation, dict):
    st.write({"recommendation": recommendation, "auto_apply": report.get("auto_apply")})

candidates = report.get("candidates", [])
if candidates:
    st.dataframe(pd.DataFrame(candidates), width="stretch")
else:
    st.caption("No parameter candidate is ready yet. Keep entering and closing mock trades.")

with st.expander("Calibration Breakdowns"):
    st.write(
        {
            "by_phase": report.get("by_phase"),
            "by_score_bucket": report.get("by_score_bucket"),
            "by_market_regime": report.get("by_market_regime"),
            "common_exit_reasons": report.get("common_exit_reasons"),
        }
    )

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
    column.dataframe(frame, width="stretch")

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
    st.dataframe(trade_frame[[col for col in visible if col in trade_frame.columns]], width="stretch")
else:
    st.caption("No mock trades entered yet.")

st.subheader("Fills")
if fills:
    st.dataframe(pd.DataFrame(fills), width="stretch")
else:
    st.caption("No fills yet.")
