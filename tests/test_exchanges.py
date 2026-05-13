import asyncio
import json
from urllib.error import URLError

from neural_grid_signal.exchanges.binance import BinanceFuturesClient
from neural_grid_signal.exchanges.okx import OKXClient


class FakeHTTPResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_okx_client_parses_ticker_and_candles(monkeypatch):
    payloads = [
        {
            "code": "0",
            "data": [
                {
                    "instId": "SOL-USDT-SWAP",
                    "last": "150",
                    "open24h": "145",
                    "high24h": "155",
                    "low24h": "140",
                    "volCcy24h": "100000000",
                }
            ],
        },
        {
            "code": "0",
            "data": [
                ["2", "102", "104", "101", "103", "11", "1100", "11000", "1"],
                ["1", "100", "103", "99", "102", "10", "1000", "10000", "1"],
            ],
        },
    ]

    def fake_urlopen(_request, timeout):
        return FakeHTTPResponse(payloads.pop(0))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = OKXClient()

    tickers = asyncio.run(client.get_all_tickers())
    candles = asyncio.run(client.get_klines("SOLUSDT", "15m", 2))

    assert tickers["SOLUSDT"].price == 150
    assert tickers["SOLUSDT"].price_change_24h > 3
    assert candles[0].open_time == 1
    assert candles[-1].quote_volume == 11000


def test_binance_client_parses_ticker_and_funding(monkeypatch):
    payloads = [
        [
            {
                "symbol": "ETHUSDT",
                "lastPrice": "3000",
                "priceChangePercent": "1.5",
                "quoteVolume": "200000000",
                "highPrice": "3050",
                "lowPrice": "2950",
            }
        ],
        [
            {
                "symbol": "ETHUSDT",
                "lastFundingRate": "0.0001",
                "nextFundingTime": "1770000000000",
            }
        ],
    ]

    def fake_urlopen(_request, timeout):
        return FakeHTTPResponse(payloads.pop(0))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = BinanceFuturesClient()

    tickers = asyncio.run(client.get_all_tickers())
    funding = asyncio.run(client.get_all_funding_rates())

    assert tickers["ETHUSDT"].volume_24h == 200000000
    assert funding["ETHUSDT"].funding_rate == 0.0001


def test_okx_client_retries_transient_http_error(monkeypatch):
    calls = 0

    def fake_urlopen(_request, timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise URLError("temporary failure")
        return FakeHTTPResponse(
            {
                "code": "0",
                "data": [
                    {
                        "instId": "SOL-USDT-SWAP",
                        "last": "150",
                        "open24h": "145",
                        "high24h": "155",
                        "low24h": "140",
                        "volCcy24h": "100000000",
                    }
                ],
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("time.sleep", lambda _seconds: None)

    tickers = asyncio.run(OKXClient().get_all_tickers())

    assert tickers["SOLUSDT"].price == 150
    assert calls == 2


def test_binance_client_retries_transient_http_error(monkeypatch):
    calls = 0

    def fake_urlopen(_request, timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise URLError("temporary failure")
        return FakeHTTPResponse(
            [
                {
                    "symbol": "ETHUSDT",
                    "lastPrice": "3000",
                    "priceChangePercent": "1.5",
                    "quoteVolume": "200000000",
                    "highPrice": "3050",
                    "lowPrice": "2950",
                }
            ]
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("time.sleep", lambda _seconds: None)

    tickers = asyncio.run(BinanceFuturesClient().get_all_tickers())

    assert tickers["ETHUSDT"].price == 3000
    assert calls == 2
