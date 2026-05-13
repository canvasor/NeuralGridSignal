from __future__ import annotations

import asyncio
import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from neural_grid_signal.http_client import urlopen_with_retries
from neural_grid_signal.models import Candle, FundingSnapshot, OpenInterestSnapshot, OrderBookSnapshot, TickerSnapshot


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default


@dataclass
class OKXClient:
    api_key: str = ""
    api_secret: str = ""
    api_passphrase: str = ""
    base_url: str = "https://www.okx.com"
    timeout_seconds: int = 15
    retry_attempts: int = 3
    retry_base_delay_seconds: float = 0.5

    async def get_swap_symbols(self) -> list[str]:
        payload = await self._get("/api/v5/public/instruments", {"instType": "SWAP"})
        symbols: list[str] = []
        for item in payload.get("data", []) if isinstance(payload, dict) else []:
            if item.get("state") and item.get("state") != "live":
                continue
            inst_id = item.get("instId", "")
            if not inst_id.endswith("-USDT-SWAP"):
                continue
            base = (item.get("ctValCcy") or item.get("baseCcy") or inst_id.split("-")[0]).upper()
            if base:
                symbols.append(f"{base}USDT")
        return sorted(set(symbols))

    async def get_all_tickers(self) -> dict[str, TickerSnapshot]:
        payload = await self._get("/api/v5/market/tickers", {"instType": "SWAP"})
        output: dict[str, TickerSnapshot] = {}
        for item in payload.get("data", []) if isinstance(payload, dict) else []:
            inst_id = item.get("instId", "")
            if not inst_id.endswith("-USDT-SWAP"):
                continue
            symbol = inst_id.split("-")[0].upper() + "USDT"
            price = _float(item.get("last"))
            open_24h = _float(item.get("open24h"))
            high = _float(item.get("high24h"))
            low = _float(item.get("low24h"))
            volume_currency = _float(item.get("volCcy24h"))
            volume_quote = _float(item.get("volCcyQuote") or item.get("volCcyQuote24h"))
            volume_24h = volume_quote if volume_quote > 0 else volume_currency * price
            change = (price - open_24h) / open_24h * 100 if open_24h > 0 else 0.0
            output[symbol] = TickerSnapshot(
                symbol=symbol,
                price=price,
                price_change_24h=change,
                volume_24h=volume_24h,
                high_24h=high,
                low_24h=low,
            )
        return output

    async def get_klines(self, symbol: str, interval: str = "15m", limit: int = 192) -> list[Candle]:
        payload = await self._get(
            "/api/v5/market/candles",
            {"instId": self.to_swap_inst_id(symbol), "bar": self._bar(interval), "limit": max(2, limit)},
        )
        rows: list[Candle] = []
        data = payload.get("data", []) if isinstance(payload, dict) else []
        for row in reversed(data[-limit:]):
            try:
                rows.append(
                    Candle(
                        open_time=int(row[0]),
                        open=float(row[1]),
                        high=float(row[2]),
                        low=float(row[3]),
                        close=float(row[4]),
                        volume=float(row[5]),
                        quote_volume=float(row[7]) if len(row) > 7 else _float(row[6] if len(row) > 6 else 0),
                        close_time=int(row[0]),
                    )
                )
            except Exception:
                continue
        return rows

    async def get_funding_rate(self, symbol: str) -> FundingSnapshot | None:
        payload = await self._get("/api/v5/public/funding-rate", {"instId": self.to_swap_inst_id(symbol)})
        data = payload.get("data", []) if isinstance(payload, dict) else []
        if not data:
            return None
        item = data[0]
        return FundingSnapshot(
            symbol=self.normalize_symbol(symbol),
            funding_rate=_float(item.get("fundingRate")),
            next_funding_time=int(_float(item.get("nextFundingTime"))),
        )

    async def get_open_interest(self, symbol: str, price: float = 0.0) -> OpenInterestSnapshot | None:
        payload = await self._get(
            "/api/v5/public/open-interest",
            {"instType": "SWAP", "instId": self.to_swap_inst_id(symbol)},
        )
        data = payload.get("data", []) if isinstance(payload, dict) else []
        if not data:
            return None
        item = data[0]
        oi_usd = _float(item.get("oiUsd"))
        oi_contracts = _float(item.get("oi"))
        if oi_usd <= 0:
            oi_usd = _float(item.get("oiCcy")) * price if price > 0 else oi_contracts * price
        return OpenInterestSnapshot(symbol=self.normalize_symbol(symbol), oi_value=oi_usd)

    async def get_orderbook(self, symbol: str, depth: int = 20) -> OrderBookSnapshot | None:
        payload = await self._get("/api/v5/market/books", {"instId": self.to_swap_inst_id(symbol), "sz": depth})
        data = payload.get("data", []) if isinstance(payload, dict) else []
        if not data:
            return None
        book = data[0]
        bids = book.get("bids", [])
        asks = book.get("asks", [])
        if not bids or not asks:
            return None
        best_bid = _float(bids[0][0])
        best_ask = _float(asks[0][0])
        bid_notional = sum(_float(row[0]) * _float(row[1]) for row in bids)
        ask_notional = sum(_float(row[0]) * _float(row[1]) for row in asks)
        return OrderBookSnapshot(self.normalize_symbol(symbol), best_bid, best_ask, bid_notional, ask_notional)

    async def close(self) -> None:
        return None

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            return await asyncio.to_thread(self._get_sync, path, params or {})
        except Exception:
            return {}

    def _get_sync(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        query = urllib.parse.urlencode({key: value for key, value in params.items() if value is not None})
        url = f"{self.base_url}{path}" + (f"?{query}" if query else "")
        request = urllib.request.Request(
            url,
            method="GET",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "NeuralGridSignal/0.1",
            },
        )
        with urlopen_with_retries(
            request,
            timeout=self.timeout_seconds,
            attempts=self.retry_attempts,
            base_delay_seconds=self.retry_base_delay_seconds,
        ) as response:
            return json.loads(response.read().decode("utf-8"))

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        symbol = symbol.upper().strip().replace("-", "")
        return symbol if symbol.endswith("USDT") else f"{symbol}USDT"

    @classmethod
    def to_swap_inst_id(cls, symbol: str) -> str:
        normalized = cls.normalize_symbol(symbol)
        return f"{normalized[:-4]}-USDT-SWAP"

    @staticmethod
    def _bar(interval: str) -> str:
        return {
            "1m": "1m",
            "3m": "3m",
            "5m": "5m",
            "15m": "15m",
            "30m": "30m",
            "1h": "1H",
            "2h": "2H",
            "4h": "4H",
            "1d": "1D",
        }.get(interval, interval)
