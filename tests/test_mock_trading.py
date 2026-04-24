from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Mapping, Sequence

from src.mock_trading.performance import compute_performance
from src.mock_trading.recommendations import recommend_entry_controls
from src.mock_trading.simulator import update_mock_trade_results
from src.providers.base import BaseMarketDataProvider, ProviderMessageHandler
from src.storage.repositories import create_mock_trade, get_mock_trade, list_mock_fills, list_mock_trades


class FakeBarsProvider(BaseMarketDataProvider):
    def __init__(self, bars: list[Mapping[str, object]]) -> None:
        self.bars = bars

    def get_assets(self):
        return []

    def get_historical_bars(self, symbols: Sequence[str], timeframe: str, start: datetime, end: datetime):
        return {symbols[0]: self.bars}

    def get_latest_bars(self, symbols: Sequence[str]):
        return {}

    def get_snapshots(self, symbols: Sequence[str]):
        return {}

    def stream_bars(self, symbols: Sequence[str], on_message: ProviderMessageHandler) -> None:
        raise NotImplementedError

    def stream_trades(self, symbols: Sequence[str], on_message: ProviderMessageHandler) -> None:
        raise NotImplementedError

    def stream_quotes(self, symbols: Sequence[str], on_message: ProviderMessageHandler) -> None:
        raise NotImplementedError

    def get_historical_news(self, symbols: Sequence[str], start: datetime, end: datetime):
        return {}

    def stream_news(self, symbols: Sequence[str], on_message: ProviderMessageHandler) -> None:
        raise NotImplementedError


def test_dynamic_recommendations_use_confidence_cash() -> None:
    controls = recommend_entry_controls(
        {
            "verdict": "Valid Trade",
            "score": 8.8,
            "phase": "Ignition",
            "entry": 10,
            "features": {"reversal_risk": 2, "liquidity_quality": 8, "distance_from_vwap_pct": 2},
        },
        available_cash=10_000,
    )

    assert controls["allocation_pct"] == 12.5
    assert controls["dollar_amount"] == 1250
    assert controls["max_hold_minutes"] == 40
    assert controls["target_1_pct"] == 60
    assert controls["target_2_pct"] == 40


def test_mock_replay_stops_out_before_target_on_same_bar() -> None:
    entered_at = datetime.now(timezone.utc) - timedelta(minutes=20)
    trade_id = _create_trade(entered_at)
    bars = [
        _bar(entered_at + timedelta(minutes=1), high=10.6, low=9.4, close=10.2),
    ]

    result = update_mock_trade_results(trade_id, FakeBarsProvider(bars))
    trade = get_mock_trade(trade_id)
    fills = list_mock_fills(trade_id)

    assert result["status"] == "closed"
    assert trade["exit_reason"] == "stop"
    assert fills[0]["fill_type"] == "stop"
    assert fills[0]["shares"] == 100


def test_mock_replay_target_one_then_breakeven_stop() -> None:
    entered_at = datetime.now(timezone.utc) - timedelta(minutes=20)
    trade_id = _create_trade(entered_at)
    bars = [
        _bar(entered_at + timedelta(minutes=1), high=10.55, low=10.0, close=10.4),
        _bar(entered_at + timedelta(minutes=2), high=10.4, low=9.95, close=10.0),
    ]

    update_mock_trade_results(trade_id, FakeBarsProvider(bars))
    trade = get_mock_trade(trade_id)
    fills = list_mock_fills(trade_id)

    assert trade["status"] == "closed"
    assert trade["exit_reason"] == "breakeven_stop"
    assert [fill["fill_type"] for fill in fills] == ["target_1", "breakeven_stop"]
    assert fills[0]["shares"] == 75
    assert fills[1]["shares"] == 25


def test_performance_metrics_compute_win_rate_and_drawdown() -> None:
    entered_at = datetime.now(timezone.utc) - timedelta(minutes=20)
    trade_id = _create_trade(entered_at)
    bars = [
        _bar(entered_at + timedelta(minutes=1), high=10.55, low=10.0, close=10.4),
        _bar(entered_at + timedelta(minutes=2), high=11.1, low=10.4, close=11.0),
    ]
    update_mock_trade_results(trade_id, FakeBarsProvider(bars))

    metrics = compute_performance(list_mock_trades(), list_mock_fills(), starting_cash=10_000)

    assert metrics["closed_trade_count"] == 1
    assert metrics["win_rate"] == 100
    assert metrics["target_1_hit_rate"] == 100
    assert metrics["target_2_hit_rate"] == 100
    assert metrics["total_pnl"] > 0


def _create_trade(entered_at: datetime) -> int:
    return create_mock_trade(
        {
            "entered_at": entered_at.isoformat(),
            "ticker": "TEST",
            "status": "open",
            "phase": "Ignition",
            "score": 8.5,
            "card": {"ticker": "TEST"},
            "dollar_amount": 1000,
            "entry": 10.0,
            "stop": 9.5,
            "current_stop": 9.5,
            "target_1": 10.5,
            "target_2": 11.0,
            "target_1_pct": 75,
            "target_2_pct": 25,
            "max_hold_minutes": 30,
            "move_stop_to_breakeven": True,
            "shares": 100,
            "remaining_shares": 100,
            "risk_per_share": 0.5,
            "entry_notional": 1000,
            "last_price": 10.0,
            "realized_pnl": 0,
            "notes": "",
        }
    )


def _bar(ts: datetime, high: float, low: float, close: float) -> dict[str, object]:
    return {"t": ts.isoformat(), "o": 10.0, "h": high, "l": low, "c": close, "v": 1000}
