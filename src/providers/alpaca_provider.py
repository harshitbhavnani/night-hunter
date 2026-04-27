from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Dict, List, Mapping, Sequence

import requests

from src.config import AppSettings, get_settings
from src.providers.base import Bar, BaseMarketDataProvider, ProviderMessageHandler, chunk_symbols


class AlpacaProvider(BaseMarketDataProvider):
    """Alpaca market-data adapter for the crypto-only MVP.

    Broad scans use batched REST calls. Streams remain reserved for caller-supplied
    shortlists so a later paid-data upgrade stays a provider capability change.
    """

    def __init__(self, settings: AppSettings | None = None) -> None:
        self.settings = settings or get_settings()
        self._session = requests.Session()
        if self.settings.alpaca_api_key and self.settings.alpaca_secret_key:
            self._session.headers.update(
                {
                    "APCA-API-KEY-ID": self.settings.alpaca_api_key,
                    "APCA-API-SECRET-KEY": self.settings.alpaca_secret_key,
                }
            )

    def get_assets(self) -> List[Mapping[str, object]]:
        if self.settings.market_mode == "crypto":
            payload = self._get_trading(
                "/v2/assets",
                {"status": "active", "asset_class": "crypto"},
            )
            return list(payload) if isinstance(payload, list) else []
        payload = self._get_trading(
            "/v2/assets",
            {"status": "active", "asset_class": "us_equity"},
        )
        return list(payload) if isinstance(payload, list) else []

    def get_historical_bars(
        self,
        symbols: Sequence[str],
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> Dict[str, List[Bar]]:
        if self.settings.market_mode == "crypto":
            return self._get_crypto_bars(symbols, timeframe, start, end)

        results: Dict[str, List[Bar]] = {}
        for chunk in chunk_symbols(symbols):
            payload = self._get_data(
                "/v2/stocks/bars",
                {
                    "symbols": ",".join(chunk),
                    "timeframe": timeframe,
                    "start": start.astimezone(timezone.utc).isoformat(),
                    "end": end.astimezone(timezone.utc).isoformat(),
                    "feed": self.settings.alpaca_feed,
                    "limit": 10000,
                    "adjustment": "raw",
                },
            )
            for symbol, bars in payload.get("bars", {}).items():
                results[symbol] = bars
        return results

    def get_latest_bars(self, symbols: Sequence[str]) -> Dict[str, Bar]:
        if self.settings.market_mode == "crypto":
            results: Dict[str, Bar] = {}
            for chunk in chunk_symbols(symbols):
                payload = self._get_data(
                    f"/v1beta3/crypto/{self.settings.crypto_location}/latest/bars",
                    {"symbols": ",".join(chunk)},
                )
                results.update(payload.get("bars", {}))
            return results

        results: Dict[str, Bar] = {}
        for chunk in chunk_symbols(symbols):
            payload = self._get_data(
                "/v2/stocks/bars/latest",
                {"symbols": ",".join(chunk), "feed": self.settings.alpaca_feed},
            )
            results.update(payload.get("bars", {}))
        return results

    def get_market_calendar(self, start: datetime, end: datetime) -> List[Mapping[str, object]]:
        payload = self._get_trading(
            "/v2/calendar",
            {
                "start": start.date().isoformat(),
                "end": end.date().isoformat(),
            },
        )
        return list(payload) if isinstance(payload, list) else []

    def get_snapshots(self, symbols: Sequence[str]) -> Dict[str, Mapping[str, object]]:
        if self.settings.market_mode == "crypto":
            return self._get_crypto_snapshots(symbols)

        results: Dict[str, Mapping[str, object]] = {}
        for chunk in chunk_symbols(symbols):
            payload = self._get_data(
                "/v2/stocks/snapshots",
                {"symbols": ",".join(chunk), "feed": self.settings.alpaca_feed},
            )
            results.update(payload)
        return results

    def get_orderbooks(self, symbols: Sequence[str]) -> Dict[str, Mapping[str, object]]:
        if self.settings.market_mode != "crypto":
            return {}
        results: Dict[str, Mapping[str, object]] = {}
        for chunk in chunk_symbols(symbols):
            payload = self._get_data(
                f"/v1beta3/crypto/{self.settings.crypto_location}/latest/orderbooks",
                {"symbols": ",".join(chunk)},
            )
            results.update(payload.get("orderbooks", {}))
        return results

    def stream_bars(self, symbols: Sequence[str], on_message: ProviderMessageHandler) -> None:
        self._stream("bars", symbols, on_message)

    def stream_trades(self, symbols: Sequence[str], on_message: ProviderMessageHandler) -> None:
        self._stream("trades", symbols, on_message)

    def stream_quotes(self, symbols: Sequence[str], on_message: ProviderMessageHandler) -> None:
        self._stream("quotes", symbols, on_message)

    def get_historical_news(
        self,
        symbols: Sequence[str],
        start: datetime,
        end: datetime,
    ) -> Dict[str, List[Mapping[str, object]]]:
        if self.settings.market_mode == "crypto":
            return {symbol: [] for symbol in symbols}

        results = {symbol: [] for symbol in symbols}
        for chunk in chunk_symbols(symbols, chunk_size=50):
            payload = self._get_data(
                "/v1beta1/news",
                {
                    "symbols": ",".join(chunk),
                    "start": start.astimezone(timezone.utc).isoformat(),
                    "end": end.astimezone(timezone.utc).isoformat(),
                    "limit": 50,
                },
            )
            for item in payload.get("news", []):
                for symbol in item.get("symbols", []):
                    if symbol in results:
                        results[symbol].append(item)
        return results

    def stream_news(self, symbols: Sequence[str], on_message: ProviderMessageHandler) -> None:
        if self.settings.market_mode == "crypto":
            return
        self._stream("news", symbols, on_message)

    def _get_crypto_bars(
        self,
        symbols: Sequence[str],
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> Dict[str, List[Bar]]:
        results: Dict[str, List[Bar]] = {}
        for chunk in chunk_symbols(symbols):
            payload = self._get_data(
                f"/v1beta3/crypto/{self.settings.crypto_location}/bars",
                {
                    "symbols": ",".join(chunk),
                    "timeframe": timeframe,
                    "start": start.astimezone(timezone.utc).isoformat(),
                    "end": end.astimezone(timezone.utc).isoformat(),
                    "limit": 10000,
                },
            )
            for symbol, bars in payload.get("bars", {}).items():
                results[symbol] = bars
        return results

    def _get_crypto_snapshots(self, symbols: Sequence[str]) -> Dict[str, Mapping[str, object]]:
        trades: Dict[str, Mapping[str, object]] = {}
        quotes: Dict[str, Mapping[str, object]] = {}
        for chunk in chunk_symbols(symbols):
            params = {"symbols": ",".join(chunk)}
            trade_payload = self._get_data(f"/v1beta3/crypto/{self.settings.crypto_location}/latest/trades", params)
            quote_payload = self._get_data(f"/v1beta3/crypto/{self.settings.crypto_location}/latest/quotes", params)
            trades.update(trade_payload.get("trades", {}))
            quotes.update(quote_payload.get("quotes", {}))

        snapshots: Dict[str, Mapping[str, object]] = {}
        for symbol in symbols:
            symbol_key = symbol.upper()
            trade = trades.get(symbol_key, {})
            quote = quotes.get(symbol_key, {})
            bid = _first_float(quote, ("bp", "bid_price", "bidPrice", "b"))
            ask = _first_float(quote, ("ap", "ask_price", "askPrice", "a"))
            snapshots[symbol_key] = {
                "latestTrade": {"p": _first_float(trade, ("p", "price"))},
                "latestQuote": {"bp": bid, "ap": ask},
            }
        return snapshots

    def _get_data(self, path: str, params: Mapping[str, object]) -> Mapping[str, object]:
        return self._request(self.settings.alpaca_data_base_url, path, params)

    def _get_trading(self, path: str, params: Mapping[str, object]) -> object:
        return self._request(self.settings.alpaca_trading_base_url, path, params)

    def _request(self, base_url: str, path: str, params: Mapping[str, object]) -> object:
        if not self.settings.live_data_enabled:
            raise RuntimeError("Alpaca live mode requires ALPACA_API_KEY and ALPACA_SECRET_KEY.")
        response = self._session.get(f"{base_url}{path}", params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    def _stream(self, stream_name: str, symbols: Sequence[str], on_message: ProviderMessageHandler) -> None:
        import websocket

        if not self.settings.live_data_enabled:
            raise RuntimeError("Alpaca streaming requires ALPACA_API_KEY and ALPACA_SECRET_KEY.")

        base = "wss://stream.data.alpaca.markets/v2/iex"
        if self.settings.market_mode == "crypto":
            base = f"wss://stream.data.alpaca.markets/v1beta3/crypto/{self.settings.crypto_location}"
        if stream_name == "news":
            base = "wss://stream.data.alpaca.markets/v1beta1/news"

        def _on_open(ws: websocket.WebSocketApp) -> None:
            ws.send(
                json.dumps(
                    {
                        "action": "auth",
                        "key": self.settings.alpaca_api_key,
                        "secret": self.settings.alpaca_secret_key,
                    }
                )
            )
            subscribe_key = {
                "bars": "bars",
                "trades": "trades",
                "quotes": "quotes",
                "news": "news",
            }[stream_name]
            ws.send(json.dumps({"action": "subscribe", subscribe_key: list(symbols)}))

        def _on_message(_: websocket.WebSocketApp, raw: str) -> None:
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                return
            if isinstance(message, list):
                for item in message:
                    on_message(item)
            else:
                on_message(message)

        websocket.WebSocketApp(base, on_open=_on_open, on_message=_on_message).run_forever()


def _first_float(mapping: Mapping[str, object], keys: Sequence[str]) -> float:
    for key in keys:
        try:
            value = float(mapping.get(key) or 0)
        except (AttributeError, TypeError, ValueError):
            value = 0.0
        if value > 0:
            return value
    return 0.0
