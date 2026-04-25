from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
DB_PATH = DATA_DIR / "night_hunter.sqlite3"


@dataclass(frozen=True)
class ScoreWeights:
    rvol: float = 0.30
    acceleration: float = 0.25
    breakout_strength: float = 0.20
    catalyst: float = 0.15
    reversal_risk: float = -0.10

    def as_dict(self) -> Dict[str, float]:
        return {
            "rvol": self.rvol,
            "acceleration": self.acceleration,
            "breakout_strength": self.breakout_strength,
            "catalyst": self.catalyst,
            "reversal_risk": self.reversal_risk,
        }


@dataclass(frozen=True)
class AppSettings:
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_data_base_url: str = "https://data.alpaca.markets"
    alpaca_trading_base_url: str = "https://paper-api.alpaca.markets"
    alpaca_feed: str = "iex"
    provider_mode: str = "live"
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    turso_database_url: str = ""
    turso_auth_token: str = ""
    db_path: Path = DB_PATH
    min_score: float = 7.5
    alert_score: float = 8.0
    shortlist_size: int = 25
    max_stop_distance_pct: float = 3.0
    min_risk_reward: float = 2.0
    max_vwap_extension_pct: float = 8.0
    scan_refresh_seconds: int = 180
    mock_starting_cash: float = 10_000.0
    basic_news_candidate_count: int = 60
    score_weights: ScoreWeights = field(default_factory=ScoreWeights)

    @property
    def live_data_enabled(self) -> bool:
        return (
            self.provider_mode.lower() == "live"
            and bool(self.alpaca_api_key)
            and bool(self.alpaca_secret_key)
        )


def _float_env(name: str, default: float) -> float:
    raw = _setting(name)
    if raw in (None, ""):
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _int_env(name: str, default: int) -> int:
    raw = _setting(name)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _setting(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value not in (None, ""):
        return value
    try:
        import streamlit as st

        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        return default
    return default


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    load_dotenv(ROOT_DIR / ".env")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    weights = ScoreWeights(
        rvol=_float_env("WEIGHT_RVOL", 0.30),
        acceleration=_float_env("WEIGHT_ACCELERATION", 0.25),
        breakout_strength=_float_env("WEIGHT_BREAKOUT", 0.20),
        catalyst=_float_env("WEIGHT_CATALYST", 0.15),
        reversal_risk=_float_env("WEIGHT_REVERSAL_RISK", -0.10),
    )
    return AppSettings(
        alpaca_api_key=_setting("ALPACA_API_KEY"),
        alpaca_secret_key=_setting("ALPACA_SECRET_KEY"),
        alpaca_data_base_url=_setting("ALPACA_DATA_BASE_URL", "https://data.alpaca.markets"),
        alpaca_trading_base_url=_setting("ALPACA_TRADING_BASE_URL", "https://paper-api.alpaca.markets"),
        alpaca_feed=_setting("ALPACA_FEED", "iex"),
        provider_mode=_setting("PROVIDER_MODE", "live"),
        telegram_bot_token=_setting("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=_setting("TELEGRAM_CHAT_ID"),
        turso_database_url=_setting("TURSO_DATABASE_URL"),
        turso_auth_token=_setting("TURSO_AUTH_TOKEN"),
        db_path=Path(_setting("NIGHT_HUNTER_DB_PATH", str(DB_PATH))),
        min_score=_float_env("MIN_SCORE", 7.5),
        alert_score=_float_env("ALERT_SCORE", 8.0),
        shortlist_size=_int_env("SHORTLIST_SIZE", 25),
        max_stop_distance_pct=_float_env("MAX_STOP_DISTANCE_PCT", 3.0),
        min_risk_reward=_float_env("MIN_RISK_REWARD", 2.0),
        max_vwap_extension_pct=_float_env("MAX_VWAP_EXTENSION_PCT", 8.0),
        scan_refresh_seconds=_int_env("SCAN_REFRESH_SECONDS", 180),
        mock_starting_cash=_float_env("MOCK_STARTING_CASH", 10_000.0),
        basic_news_candidate_count=_int_env("BASIC_NEWS_CANDIDATE_COUNT", 60),
        score_weights=weights,
    )


def clear_settings_cache() -> None:
    get_settings.cache_clear()
