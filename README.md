# Night Hunter

Night Hunter is a Python + Streamlit decision-support dashboard for one crypto momentum trade idea at a time. It is not an auto-trader. Real orders are never placed; mock trades are replayed from Alpaca crypto 1-minute bars.

Version 1 is crypto-only. Alpaca provides historical momentum bars; Kraken public market data provides the execution-venue quote/depth gate so a setup must be tradable on the venue assumption you plan to use.

## Run Locally

```bash
cd night-hunter
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
streamlit run app/streamlit_app.py
```

Local URL:

```text
http://localhost:8501
```

## Required Secrets

For local development, copy `.env.example` to `.env`. For Streamlit Community Cloud, add the same keys in the app's Secrets settings.

```toml
PROVIDER_MODE = "live"
MARKET_MODE = "crypto"
ALPACA_API_KEY = "..."
ALPACA_SECRET_KEY = "..."

CRYPTO_LOCATION = "us"
CRYPTO_UNIVERSE_MODE = "dynamic_safe_fallback"
CRYPTO_SYMBOLS = "BTC/USD,ETH/USD,SOL/USD,AVAX/USD,LINK/USD,UNI/USD,AAVE/USD,DOGE/USD,LTC/USD,BCH/USD"
CRYPTO_SCAN_MINUTES = "90"
CRYPTO_MIN_QUOTE_VOLUME = "50000"
CRYPTO_MAX_SPREAD_PCT = "0.35"
CRYPTO_MIN_ORDERBOOK_NOTIONAL_DEPTH = "25000"
CRYPTO_DEPTH_BPS = "25"

VENUE_PROVIDER = "kraken"
KRAKEN_BASE_URL = "https://api.kraken.com"
KRAKEN_MAX_SPREAD_PCT = "0.35"
KRAKEN_MAX_QUOTE_AGE_SECONDS = "30"
KRAKEN_MIN_ORDERBOOK_NOTIONAL_DEPTH = "25000"
MAX_ALPACA_VENUE_DEVIATION_PCT = "0.50"

TURSO_DATABASE_URL = "..."
TURSO_AUTH_TOKEN = "..."

```

Turso/libSQL is optional for local development. If Turso credentials are blank, Night Hunter uses `data/night_hunter.sqlite3`. For Streamlit Cloud, configure Turso so mock-trade history survives app restarts and redeploys.

## Crypto Universe

The active universe defaults to dynamic Alpaca crypto discovery. Night Hunter fetches active/tradable Alpaca crypto assets, keeps USD pairs, and uses `CRYPTO_SYMBOLS` only as the safe fallback list or when `CRYPTO_UNIVERSE_MODE=fixed`. The scanner:

- refreshes pair/daily quote-volume cache locally,
- filters by recent quote volume so tiny illiquid coins cannot rank just because they moved sharply,
- uses Alpaca quote spread and an Alpaca orderbook depth proxy as pre-ranking liquidity gates,
- uses Kraken public bid/ask as the final execution-venue spread and tradability gate,
- uses Kraken public orderbook depth as the final venue-depth gate,
- scans the latest rolling window, default `90` minutes,
- requests Alpaca crypto bars in batches,
- requests Kraken AssetPairs, Ticker, and Depth for venue confirmation,
- ranks by abnormal volume, acceleration, breakout strength, spread/liquidity, and low reversal risk,
- does not require equity-style catalysts.

## Strategy Shape

Crypto-first default score:

```text
Momentum Score =
0.35 * RVOL_score
+ 0.30 * Acceleration_score
+ 0.25 * Breakout_strength_score
- 0.10 * Reversal_risk_score
```

Hard vetoes reject weak scores, exhaustion/dump phases, wide stops, poor risk/reward, poor spread/liquidity, excessive VWAP extension, crypto spreads above the configured max, missing Kraken quotes, non-tradable Kraken assets, stale Kraken quotes, wide Kraken spreads, low Kraken depth, or excessive Alpaca/Kraken price deviation.

## Mock Trading

Valid trade cards include **Enter Mock Trade**. The app recommends editable controls:

- dollar amount based on confidence percent of available mock cash,
- max hold minutes based on phase, score, liquidity, VWAP extension, and reversal risk,
- Target 1 / Target 2 split.

Crypto quantities are fractional. The mock long entry defaults to Kraken ask when the venue gate passes. After Target 1 fills, the remaining stop moves to breakeven by default. “Automatic selling” means simulated exits only.

## Pages

- **Dashboard**: run scan, best trade-card summary, shortlist, and quick performance snapshot.
- **Scanner**: deeper shortlist table with diagnostics and selected-symbol routing to Trade Card.
- **Trade Card**: one execution card or **No Trade Tonight**, plus mock entry form.
- **Trade History**: mock trades/fills with settings snapshots for later pattern review.
- **Settings**: thresholds, crypto universe settings, score weights, and mock bankroll.
- **Performance**: mock equity curve, P/L, win rate, average R, expectancy, drawdown, target hit rates, hold time, and trade/fill logs.

## Tests

```bash
pytest
```

Coverage includes provider contract with mocked Alpaca crypto responses, crypto universe filtering, scoring, phase, veto, execution, mock replay, and dashboard metrics.

## Deployment Notes

Deploy the repo to Streamlit Community Cloud with entrypoint:

```text
app/streamlit_app.py
```

Add Alpaca and Turso secrets in Streamlit Cloud before running scans. The app shows setup instructions instead of scanning when Alpaca credentials are missing.
