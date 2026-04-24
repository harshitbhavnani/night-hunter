from __future__ import annotations

from typing import Mapping, Sequence, Tuple


CATALYST_TERMS = (
    "earnings",
    "guidance",
    "contract",
    "fda",
    "approval",
    "partnership",
    "acquisition",
    "launch",
    "upgrade",
    "milestone",
    "award",
)


def catalyst_signal(news_items: Sequence[Mapping[str, object]]) -> Tuple[bool, str, float]:
    if not news_items:
        return False, "No fresh catalyst found in Alpaca news.", 0.0
    headline = str(news_items[0].get("headline") or news_items[0].get("summary") or "Fresh news detected")
    text = " ".join(str(item.get("headline", "")) for item in news_items).lower()
    has_keyword = any(term in text for term in CATALYST_TERMS)
    score = 10.0 if has_keyword else 6.0
    return True, headline, score

