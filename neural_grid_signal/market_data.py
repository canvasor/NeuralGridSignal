from __future__ import annotations

import asyncio
import logging

from neural_grid_signal.config import Settings
from neural_grid_signal.exchanges.binance import BinanceFuturesClient
from neural_grid_signal.exchanges.okx import OKXClient
from neural_grid_signal.models import SymbolMarketData

logger = logging.getLogger(__name__)


class CombinedMarketDataProvider:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.okx = OKXClient(
            api_key=settings.okx_api_key,
            api_secret=settings.okx_api_secret,
            api_passphrase=settings.okx_api_passphrase,
        )
        self.binance = BinanceFuturesClient(
            api_key=settings.binance_api_key,
            api_secret=settings.binance_api_secret,
        )

    async def fetch_candidates(self, limit: int) -> list[SymbolMarketData]:
        okx_tickers = await self.okx.get_all_tickers()
        if not okx_tickers:
            return []
        ranked = sorted(
            okx_tickers.values(),
            key=lambda item: item.volume_24h,
            reverse=True,
        )
        ranked = [item for item in ranked if item.volume_24h >= self.settings.min_volume_24h / 2][: max(1, limit)]

        binance_tickers, binance_funding = await asyncio.gather(
            self.binance.get_all_tickers(),
            self.binance.get_all_funding_rates(),
            return_exceptions=False,
        )

        rows = await asyncio.gather(
            *[self._build_symbol_row(item, binance_tickers, binance_funding) for item in ranked],
            return_exceptions=True,
        )
        output: list[SymbolMarketData] = []
        for row in rows:
            if isinstance(row, SymbolMarketData):
                output.append(row)
            elif isinstance(row, Exception):
                logger.debug("candidate skipped: %s", row)
        return output

    async def _build_symbol_row(self, ticker, binance_tickers, binance_funding) -> SymbolMarketData | None:
        symbol = ticker.symbol
        okx_15m, okx_1h, okx_funding, okx_oi, orderbook = await asyncio.gather(
            self.okx.get_klines(symbol, "15m", 192),
            self.okx.get_klines(symbol, "1h", 168),
            self.okx.get_funding_rate(symbol),
            self.okx.get_open_interest(symbol, ticker.price),
            self.okx.get_orderbook(symbol, 20),
        )
        if len(okx_15m) < 24:
            return None
        binance_ticker = binance_tickers.get(symbol)
        binance_15m = []
        binance_oi = None
        if binance_ticker:
            binance_15m, binance_oi = await asyncio.gather(
                self.binance.get_klines(symbol, "15m", 192),
                self.binance.get_open_interest(symbol, binance_ticker.price),
            )
        return SymbolMarketData(
            symbol=symbol,
            okx_ticker=ticker,
            okx_candles_15m=okx_15m,
            okx_candles_1h=okx_1h,
            okx_funding=okx_funding,
            okx_oi=okx_oi,
            okx_orderbook=orderbook,
            binance_ticker=binance_ticker,
            binance_candles_15m=binance_15m,
            binance_funding=binance_funding.get(symbol),
            binance_oi=binance_oi,
        )

    async def close(self) -> None:
        await asyncio.gather(self.okx.close(), self.binance.close(), return_exceptions=True)
