from __future__ import annotations

from datetime import date
from typing import Mapping

from src.storage.repositories import add_journal_entry


def log_trade_card_to_journal(card: Mapping[str, object], notes: str = "") -> None:
    add_journal_entry(
        {
            "trade_date": date.today().isoformat(),
            "ticker": card.get("ticker"),
            "phase": card.get("phase"),
            "score": card.get("score"),
            "catalyst": card.get("catalyst_summary"),
            "entry": card.get("entry"),
            "stop": card.get("stop"),
            "target_1": card.get("target_1"),
            "target_2": card.get("target_2"),
            "exit": None,
            "pnl": None,
            "notes": notes,
        }
    )

