from __future__ import annotations

from typing import Mapping

import requests

from src.config import AppSettings, get_settings


def should_send_trade_alert(card: Mapping[str, object], settings: AppSettings | None = None) -> bool:
    settings = settings or get_settings()
    return (
        float(card.get("score", 0)) >= settings.alert_score
        and str(card.get("phase")) in {"Ignition", "Expansion"}
        and str(card.get("verdict")) == "Valid Trade"
        and float(card.get("risk_reward", 0)) >= settings.min_risk_reward
    )


def send_telegram_alert(message: str, settings: AppSettings | None = None) -> bool:
    settings = settings or get_settings()
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return False
    response = requests.post(
        f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
        json={"chat_id": settings.telegram_chat_id, "text": message, "parse_mode": "Markdown"},
        timeout=10,
    )
    response.raise_for_status()
    return True

