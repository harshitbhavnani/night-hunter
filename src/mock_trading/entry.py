from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Mapping

from src.storage.repositories import create_mock_trade


def enter_mock_trade(
    card: Mapping[str, object],
    dollar_amount: float,
    max_hold_minutes: int,
    target_1_pct: float,
    target_2_pct: float,
    entry: float | None = None,
    stop: float | None = None,
    target_1: float | None = None,
    target_2: float | None = None,
    notes: str = "",
) -> int:
    entry = float(entry if entry is not None else card.get("entry", 0))
    stop = float(stop if stop is not None else card.get("stop", 0))
    target_1 = float(target_1 if target_1 is not None else card.get("target_1", 0))
    target_2 = float(target_2 if target_2 is not None else card.get("target_2", 0))
    shares = math.floor(float(dollar_amount) / entry) if entry > 0 else 0
    if shares <= 0:
        raise ValueError("Dollar amount is too small to buy at least one mock share.")
    if stop >= entry:
        raise ValueError("Stop must be below entry.")
    if target_1 <= entry or target_2 <= entry:
        raise ValueError("Targets must be above entry.")
    if int(round(target_1_pct + target_2_pct)) != 100:
        raise ValueError("Target split must add to 100%.")

    now = datetime.now(timezone.utc).isoformat()
    risk_per_share = entry - stop
    return create_mock_trade(
        {
            "entered_at": now,
            "ticker": card.get("ticker"),
            "status": "open",
            "phase": card.get("phase"),
            "score": card.get("score"),
            "card": dict(card),
            "dollar_amount": round(shares * entry, 2),
            "entry": entry,
            "stop": stop,
            "current_stop": stop,
            "target_1": target_1,
            "target_2": target_2,
            "target_1_pct": target_1_pct,
            "target_2_pct": target_2_pct,
            "max_hold_minutes": max_hold_minutes,
            "move_stop_to_breakeven": True,
            "shares": shares,
            "remaining_shares": shares,
            "risk_per_share": risk_per_share,
            "entry_notional": round(shares * entry, 2),
            "last_price": entry,
            "realized_pnl": 0,
            "notes": notes,
        }
    )
