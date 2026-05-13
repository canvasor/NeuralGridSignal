from __future__ import annotations

import asyncio
import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from neural_grid_signal.models import Candle, FundingSnapshot, OpenInterestSnapshot, TickerSnapshot


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default


@dataclass
class BinanceFuturesClient:
    api_key: str = ""
    api_secret: str = ""
    base_url: str = "https://fapi.binance.com"
    timeout_seconds: int = 15

    async def get_symbols(self) -> list[str]:
        payload = await self._get("/fapi/v1/exchangeInfo")
        rows = []
        for item in payload.get("symbols", []) if isinstance(payload, dict) else []:
            if item.get("contractType") == "PERPETUAL" and item.get("quoteAsset") == "USDT" and item.get("status") == "TRADING":
                rows.append(item["symbol"])
        return rows

    async def get_all_tickers(self) -> dict[str, TickerSnapshot]:
        data = await self._get("/fapi/v1/ticker/24hr")
        output: dict[str, TickerSnapshot] = {}
        if not isinstance(data, list):
            return output
        for item in data:
            symbol = item.get("symbol", "")
            if not symbol.endswith("USDT"):
                continue
            output[symbol] = TickerSnapshot(
                symbol=symbol,
                price=_float(item.get("lastPrice")),
                price_change_24h=_float(item.get("priceChangePercent")),
                volume_24h=_float(item.get("quoteVolume")),
                high_24h=_float(item.get("highPrice")),
                low_24h=_float(item.get("lowPrice")),
            )
        return output

    async def get_klines(self, symbol: str, interval: str = "15m", limit: int = 192) -> list[Candle]:
        data = await self._get("/fapi/v1/klines", {"symbol": symbol.upper(), "interval": interval, "limit": limit})
        output: list[Candle] = []
        if not isinstance(data, list):
            return output
        for row in data:
            try:
                output.append(
                    Candle(
                        open_time=int(row[0]),
                        open=float(row[1]),
                        high=float(row[2]),
                        low=float(row[3]),
                        close=float(row[4]),
                        volume=float(row[5]),
                        close_time=int(row[6]),
                        quote_volume=float(row[7]),
                    )
                )
            except Exception:
                continue
        return output

    async def get_all_funding_rates(self) -> dict[str, FundingSnapshot]:
        data = await self._get("/fapi/v1/premiumIndex")
        output: dict[str, FundingSnapshot] = {}
        if not isinstance(data, list):
            return output
        for item in data:
            symbol = item.get("symbol", "")
            if symbol.endswith("USDT"):
                output[symbol] = FundingSnapshot(
                    symbol=symbol,
                    funding_rate=_float(item.get("lastFundingRate")),
                    next_funding_time=int(_float(item.get("nextFundingTime"))),
                )
        return output

    async def get_open_interest(self, symbol: str, price: float = 0.0) -> OpenInterestSnapshot | None:
        payload = await self._get("/fapi/v1/openInterest", {"symbol": symbol.upper()})
        if not isinstance(payload, dict) or not payload:
            return None
        oi_coins = _float(payload.get("openInterest"))
        return OpenInterestSnapshot(symbol=symbol.upper(), oi_value=oi_coins * price)

    async def close(self) -> None:
        return None

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            return await asyncio.to_thread(self._get_sync, path, params or {})
        except Exception:
            return {}

    def _get_sync(self, path: str, params: dict[str, Any]) -> Any:
        query = urllib.parse.urlencode({key: value for key, value in params.items() if value is not None})
        url = f"{self.base_url}{path}" + (f"?{query}" if query else "")
        headers = {"Accept": "application/json", "User-Agent": "NeuralGridSignal/0.1"}
        if self.api_key:
            headers["X-MBX-APIKEY"] = self.api_key
        request = urllib.request.Request(url, method="GET", headers=headers)
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
