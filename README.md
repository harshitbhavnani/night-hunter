# Night Hunter

Night Hunter is a Python + Streamlit decision-support dashboard for one U.S. equity momentum trade per night. It is not an auto-trader. Real execution stays manual in Robinhood Legend; the app tracks simulated/mock execution separately.

Version 1 is real-data-only and uses Alpaca Basic/IEX first. IEX is useful for the MVP workflow, but it is not consolidated SIP tape and can miss market-wide volume, quotes, and breakouts.

## App Location

```bash
cd night-hunter
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
ALPACA_API_KEY = "..."
ALPACA_SECRET_KEY = "..."
ALPACA_FEED = "iex"
BASIC_MIN_IEX_AVG_DAILY_VOLUME = "10000"
BASIC_MAX_UNIVERSE_SYMBOLS = "800"

TURSO_DATABASE_URL = "..."
TURSO_AUTH_TOKEN = "..."

TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID = ""
```

Turso/libSQL is optional for local development. If Turso credentials are blank, Night Hunter uses `data/night_hunter.sqlite3`. For Streamlit Cloud, configure Turso so mock-trade history survives app restarts and redeploys.

## Real-Data Universe

Alpaca Free does not provide market cap fundamentals, and v1 intentionally does not add a second vendor. The v1 universe therefore filters by:

- active/tradable U.S. equities from Alpaca assets,
- common-stock style exclusions,
- price from `2` to `50`,
- Basic/IEX 30-day average daily IEX volume at least `10K` by default,
- spread/liquidity quality during scan.

The original demo seed file and synthetic provider behavior have been removed.

The app caches Alpaca assets and daily IEX ADV once per day to stay within Basic limits. Live scans use the cached universe, then request snapshots and 1-minute bars only for filtered symbols. Catalyst news is fetched only after coarse structural ranking. Scanner diagnostics show whether a scan failed at asset discovery, price/volume filtering, minute-bar availability, or feature generation.

## Strategy Shape

The ranker emphasizes early abnormal behavior rather than daily percent gain:

```text
Momentum Score =
0.30 * RVOL_score
+ 0.25 * Acceleration_score
+ 0.20 * Breakout_strength_score
+ 0.15 * Catalyst_score
- 0.10 * Reversal_risk_score
```

Hard vetoes reject setups with weak score, exhaustion/dump phase, missing catalyst or exceptional structure, stop distance above 3%, risk/reward below 1:2, poor spread/liquidity, or excessive VWAP extension.

## Mock Trading

Valid trade cards include **Enter Mock Trade**. The app recommends editable controls:

- dollar amount based on confidence percent of available mock cash,
- max hold minutes based on phase, score, liquidity, VWAP extension, and reversal risk,
- Target 1 / Target 2 split.

Default mock bankroll is `$10,000`. After Target 1 fills, the remaining stop moves to breakeven by default. Open mock trades are replayed with Alpaca 1-minute bars; “automatic selling” means simulated exits only, never real orders.

Mock exits are labeled IEX-simulated. Upgrade to Alpaca Algo Trader Plus before treating mock results as evidence for real-money scaling, especially if Night Hunter disagrees with Robinhood charts or the strategy depends on fast breakouts, tight spreads, or full-market RVOL.

## Pages

- **Scanner**: real-data shortlist table with universe refresh and scan diagnostics.
- **Trade Card**: one valid execution card or **No Trade Tonight**, plus mock entry form.
- **Trade History**: mock trades/fills with settings snapshots for later pattern review.
- **Settings**: thresholds, Basic/IEX universe settings, score weights, and mock bankroll.
- **Performance**: mock equity curve, P/L, win rate, average R, expectancy, drawdown, target hit rates, hold time, and trade/fill logs.

## Tests

```bash
pytest
```

Coverage includes provider contract with mocked Alpaca responses, universe filtering, scoring, phase, veto, execution, mock replay, and dashboard metrics.

## Deployment Notes

Deploy the repo to Streamlit Community Cloud with entrypoint:

```text
app/streamlit_app.py
```

Add Alpaca and Turso secrets in Streamlit Cloud before running scans. The app shows setup instructions instead of scanning when Alpaca credentials are missing.

In Streamlit Cloud's **Advanced settings**, choose Python `3.12` if available. If your app was created with Python `3.14`, delete and redeploy it with Python `3.12`; Streamlit Cloud does not use `runtime.txt` for Python version changes after deployment. The requirements file avoids direct NumPy/PyArrow pins so the cloud builder can choose compatible wheels.
