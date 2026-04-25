from __future__ import annotations

from src.config import AppSettings


def build_settings_snapshot(settings: AppSettings) -> dict[str, object]:
    feed = settings.alpaca_feed.lower()
    return {
        "provider_mode": settings.provider_mode,
        "alpaca_feed": feed,
        "data_confidence": "Basic/IEX" if feed == "iex" else "SIP/Plus",
        "limitations": "Not consolidated SIP tape" if feed == "iex" else "Consolidated SIP feed",
        "min_score": settings.min_score,
        "alert_score": settings.alert_score,
        "shortlist_size": settings.shortlist_size,
        "max_stop_distance_pct": settings.max_stop_distance_pct,
        "min_risk_reward": settings.min_risk_reward,
        "max_vwap_extension_pct": settings.max_vwap_extension_pct,
        "mock_starting_cash": settings.mock_starting_cash,
        "basic_news_candidate_count": settings.basic_news_candidate_count,
        "score_weights": settings.score_weights.as_dict(),
    }
