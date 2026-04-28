from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, Tuple

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
DB_PATH = DATA_DIR / "night_hunter.sqlite3"


@dataclass(frozen=True)
class ScoreWeights:
    rvol: float = 0.35
    acceleration: float = 0.30
    breakout_strength: float = 0.25
    catalyst: float = 0.00
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
    market_mode: str = "crypto"
    crypto_symbols: Tuple[str, ...] = (
        "BTC/USD",
        "ETH/USD",
        "SOL/USD",
        "AVAX/USD",
        "LINK/USD",
        "UNI/USD",
        "AAVE/USD",
        "DOGE/USD",
        "LTC/USD",
        "BCH/USD",
    )
    crypto_universe_mode: str = "dynamic_safe_fallback"
    crypto_location: str = "us"
    crypto_scan_minutes: int = 90
    crypto_min_quote_volume: float = 50_000.0
    crypto_max_spread_pct: float = 0.35
    crypto_min_orderbook_notional_depth: float = 25_000.0
    crypto_depth_bps: float = 25.0
    venue_provider: str = "kraken"
    kraken_base_url: str = "https://api.kraken.com"
    kraken_max_spread_pct: float = 0.35
    kraken_max_quote_age_seconds: int = 30
    max_alpaca_venue_deviation_pct: float = 0.50
    kraken_min_orderbook_notional_depth: float = 25_000.0
    turso_database_url: str = ""
    turso_auth_token: str = ""
    db_path: Path = DB_PATH
    min_score: float = 7.5
    shortlist_size: int = 25
    max_stop_distance_pct: float = 3.0
    min_risk_reward: float = 2.0
    max_vwap_extension_pct: float = 8.0
    scan_refresh_seconds: int = 180
    mock_starting_cash: float = 10_000.0
    mock_fee_bps: float = 40.0
    mock_slippage_bps: float = 5.0
    calibration_min_trades: int = 30
    calibration_holdout_pct: float = 30.0
    basic_news_candidate_count: int = 60
    basic_min_iex_avg_daily_volume: float = 10_000.0
    basic_max_universe_symbols: int = 800
    score_weights: ScoreWeights = field(default_factory=ScoreWeights)

    @property
    def live_data_enabled(self) -> bool:
        return (
            self.provider_mode.lower() == "live"
            and bool(self.alpaca_api_key)
            and bool(self.alpaca_secret_key)
        )

    @property
    def venue_quote_gate_ready(self) -> bool:
        return self.venue_provider.lower() == "kraken" and bool(self.kraken_base_url)


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


def _bool_env(name: str, default: bool) -> bool:
    raw = _setting(name)
    if raw in (None, ""):
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


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


def _symbols_env(name: str, default: Tuple[str, ...]) -> Tuple[str, ...]:
    raw = _setting(name, ",".join(default))
    symbols = tuple(symbol.strip().upper() for symbol in raw.split(",") if symbol.strip())
    return symbols or default


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    load_dotenv(ROOT_DIR / ".env")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    weights = ScoreWeights(
        rvol=_float_env("WEIGHT_RVOL", 0.35),
        acceleration=_float_env("WEIGHT_ACCELERATION", 0.30),
        breakout_strength=_float_env("WEIGHT_BREAKOUT", 0.25),
        catalyst=_float_env("WEIGHT_CATALYST", 0.0),
        reversal_risk=_float_env("WEIGHT_REVERSAL_RISK", -0.10),
    )
    return AppSettings(
        alpaca_api_key=_setting("ALPACA_API_KEY"),
        alpaca_secret_key=_setting("ALPACA_SECRET_KEY"),
        alpaca_data_base_url=_setting("ALPACA_DATA_BASE_URL", "https://data.alpaca.markets"),
        alpaca_trading_base_url=_setting("ALPACA_TRADING_BASE_URL", "https://paper-api.alpaca.markets"),
        alpaca_feed=_setting("ALPACA_FEED", "iex"),
        provider_mode=_setting("PROVIDER_MODE", "live"),
        market_mode=_setting("MARKET_MODE", "crypto").lower(),
        crypto_symbols=_symbols_env(
            "CRYPTO_SYMBOLS",
            ("BTC/USD", "ETH/USD", "SOL/USD", "AVAX/USD", "LINK/USD", "UNI/USD", "AAVE/USD", "DOGE/USD", "LTC/USD", "BCH/USD"),
        ),
        crypto_universe_mode=_setting("CRYPTO_UNIVERSE_MODE", "dynamic_safe_fallback").lower(),
        crypto_location=_setting("CRYPTO_LOCATION", "us").lower(),
        crypto_scan_minutes=_int_env("CRYPTO_SCAN_MINUTES", 90),
        crypto_min_quote_volume=_float_env("CRYPTO_MIN_QUOTE_VOLUME", 50_000.0),
        crypto_max_spread_pct=_float_env("CRYPTO_MAX_SPREAD_PCT", 0.35),
        crypto_min_orderbook_notional_depth=_float_env("CRYPTO_MIN_ORDERBOOK_NOTIONAL_DEPTH", 25_000.0),
        crypto_depth_bps=_float_env("CRYPTO_DEPTH_BPS", 25.0),
        venue_provider=_setting("VENUE_PROVIDER", "kraken").lower(),
        kraken_base_url=_setting("KRAKEN_BASE_URL", "https://api.kraken.com").rstrip("/"),
        kraken_max_spread_pct=_float_env("KRAKEN_MAX_SPREAD_PCT", 0.35),
        kraken_max_quote_age_seconds=_int_env("KRAKEN_MAX_QUOTE_AGE_SECONDS", 30),
        max_alpaca_venue_deviation_pct=_float_env("MAX_ALPACA_VENUE_DEVIATION_PCT", 0.50),
        kraken_min_orderbook_notional_depth=_float_env("KRAKEN_MIN_ORDERBOOK_NOTIONAL_DEPTH", 25_000.0),
        turso_database_url=_setting("TURSO_DATABASE_URL"),
        turso_auth_token=_setting("TURSO_AUTH_TOKEN"),
        db_path=Path(_setting("NIGHT_HUNTER_DB_PATH", str(DB_PATH))),
        min_score=_float_env("MIN_SCORE", 7.5),
        shortlist_size=_int_env("SHORTLIST_SIZE", 25),
        max_stop_distance_pct=_float_env("MAX_STOP_DISTANCE_PCT", 3.0),
        min_risk_reward=_float_env("MIN_RISK_REWARD", 2.0),
        max_vwap_extension_pct=_float_env("MAX_VWAP_EXTENSION_PCT", 8.0),
        scan_refresh_seconds=_int_env("SCAN_REFRESH_SECONDS", 180),
        mock_starting_cash=_float_env("MOCK_STARTING_CASH", 10_000.0),
        mock_fee_bps=_float_env("MOCK_FEE_BPS", 40.0),
        mock_slippage_bps=_float_env("MOCK_SLIPPAGE_BPS", 5.0),
        calibration_min_trades=_int_env("CALIBRATION_MIN_TRADES", 30),
        calibration_holdout_pct=_float_env("CALIBRATION_HOLDOUT_PCT", 30.0),
        basic_news_candidate_count=_int_env("BASIC_NEWS_CANDIDATE_COUNT", 60),
        basic_min_iex_avg_daily_volume=_float_env("BASIC_MIN_IEX_AVG_DAILY_VOLUME", 10_000.0),
        basic_max_universe_symbols=_int_env("BASIC_MAX_UNIVERSE_SYMBOLS", 800),
        score_weights=weights,
    )


def clear_settings_cache() -> None:
    get_settings.cache_clear()
