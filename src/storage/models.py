from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class JournalEntry:
    trade_date: str
    ticker: str
    phase: str
    score: float
    catalyst: str
    entry: float
    stop: float
    target_1: float
    target_2: float
    exit: float | None
    pnl: float | None
    notes: str

