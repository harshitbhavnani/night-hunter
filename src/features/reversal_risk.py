from __future__ import annotations

from statistics import pstdev
from typing import Mapping, Sequence

from src.features.returns import close_values
from src.features.vwap import distance_from_vwap_pct


def wick_rejection_score(bars: Sequence[Mapping[str, object]], lookback: int = 5) -> float:
    recent = bars[-lookback:]
    if not recent:
        return 0.0
    scores = []
    for bar in recent:
        high = float(bar.get("h", 0))
        low = float(bar.get("l", 0))
        close = float(bar.get("c", 0))
        open_price = float(bar.get("o", close))
        candle_range = max(0.01, high - low)
        upper_wick = high - max(open_price, close)
        scores.append(max(0.0, min(1.0, upper_wick / candle_range)))
    return sum(scores) / len(scores) * 10


def short_term_volatility(bars: Sequence[Mapping[str, object]], lookback: int = 15) -> float:
    closes = close_values(bars[-lookback:])
    if len(closes) < 3:
        return 0.0
    returns = [(closes[i] - closes[i - 1]) / closes[i - 1] * 100 for i in range(1, len(closes)) if closes[i - 1]]
    return pstdev(returns) if len(returns) > 1 else 0.0


def reversal_risk_score(
    bars: Sequence[Mapping[str, object]],
    price: float,
    vwap: float,
    liquidity_score: float,
) -> float:
    wick = wick_rejection_score(bars)
    extension = max(0.0, distance_from_vwap_pct(price, vwap) - 3.0)
    volatility = short_term_volatility(bars)
    liquidity_penalty = max(0.0, 6.0 - liquidity_score)
    return max(0.0, min(10.0, wick * 0.45 + extension * 0.45 + volatility * 0.8 + liquidity_penalty * 0.5))

