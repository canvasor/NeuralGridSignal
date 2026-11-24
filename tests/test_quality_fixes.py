import asyncio
from dataclasses import replace

from neural_grid_signal.backtest import simulate_grid
from neural_grid_signal.models import Candle
from neural_grid_signal.runner import GridSignalRunner
from neural_grid_signal.config import Settings
from test_runner import FakeMarketDataProvider,FakeNotifier


def candles(values):
    return [Candle(i,p,p+1,p-1,p,1000,100000) for i,p in enumerate(values)]


def test_evaluation_grid_anchor_does_not_see_last_price():
    a=simulate_grid(candles([100]*20+[101]*10),6,2,500)
    b=simulate_grid(candles([100]*20+[140]*10),6,2,500)
    assert a.evaluation_lower_price==b.evaluation_lower_price
    assert a.evaluation_upper_price==b.evaluation_upper_price


def test_losses_are_not_clamped_to_zero_and_inventory_is_marked():
    r=simulate_grid(candles([100]*20+list(range(99,70,-1))),6,2,500)
    assert r.net_equity_return_pct<0
    assert r.max_drawdown_pct>0


def test_low_score_or_wait_is_not_published_even_if_preflight_passes(tmp_path):
    runner=GridSignalRunner(Settings(output_dir=tmp_path,dry_run=True),FakeMarketDataProvider(),FakeNotifier())
    rows=asyncio.run(runner.market_data_provider.fetch_candidates(1));s=runner.scorer.score(rows[0]);s.hard_blocked=False;s.nofx_preflight.verdict='pass';s.nofx_preflight.source='binance_5m'
    for score,direction in [(33.35,'long_bias'),(90,'wait')]:
        runner.scorer.rank=lambda _: [replace(s,final_score=score,direction=direction)]
        result=asyncio.run(runner.run_once())
        assert result.outcome=='no_signal'


def test_missing_execution_data_cannot_publish(tmp_path):
    runner=GridSignalRunner(Settings(output_dir=tmp_path,dry_run=True),FakeMarketDataProvider(),FakeNotifier())
    rows=asyncio.run(runner.market_data_provider.fetch_candidates(1));s=runner.scorer.score(rows[0]);s.final_score=90;s.nofx_preflight.source='okx_5m'
    assert 'execution_data_missing' in runner.selection_rejections(s)


def test_snapshot_published_as_complete_json_with_policy(tmp_path):
    import json
    runner=GridSignalRunner(Settings(output_dir=tmp_path,dry_run=True),FakeMarketDataProvider(),FakeNotifier())
    result=asyncio.run(runner.run_once())
    snapshot=json.loads(result.snapshot_path.read_text())
    assert snapshot['selection_policy']['minimum_score']==55
    assert snapshot['candidate_diagnostics']
    assert not list(tmp_path.rglob('*.tmp'))


def test_binance_excludes_unclosed_candle():
    from neural_grid_signal.exchanges.binance import BinanceFuturesClient
    import time
    client=BinanceFuturesClient()
    async def get(*args):
        return [[1,100,101,99,100,1,int(time.time()*1000)-1000,100], [2,100,101,99,100,1,int(time.time()*1000)+60000,100]]
    client._get=get
    assert len(asyncio.run(client.get_klines('BTCUSDT')))==1


def test_okx_excludes_unconfirmed_candle_and_keeps_recent_closed():
    from neural_grid_signal.exchanges.okx import OKXClient
    client=OKXClient()
    async def get(*args):
        return {'data':[[3,100,101,99,100,1,100,100,'0'],[2,100,101,99,100,1,100,100,'1'],[1,100,101,99,100,1,100,100,'1']]}
    client._get=get
    assert [x.open_time for x in asyncio.run(client.get_klines('BTCUSDT',limit=2))]==[1,2]


def test_scheduler_survives_failure_and_retries_at_next_schedule(monkeypatch):
    from neural_grid_signal import scheduler
    from datetime import datetime
    from zoneinfo import ZoneInfo
    async def scenario():
        stop=asyncio.Event();calls=[];now=datetime(2026,11,24,tzinfo=ZoneInfo('Asia/Shanghai'))
        monkeypatch.setattr(scheduler,'next_run_after',lambda *args:now)
        async def job():
            calls.append(1)
            if len(calls)==1:raise RuntimeError('failed')
            stop.set()
        await asyncio.wait_for(scheduler.run_forever(job,('08:00',),now.tzinfo,now_fn=lambda:now,stop_event=stop),timeout=.2)
        assert len(calls)==2
    asyncio.run(scenario())


def test_stale_binance_execution_data_is_not_reused():
    from neural_grid_signal.exchanges.binance import BinanceFuturesClient
    client=BinanceFuturesClient()
    async def get(*args):return [[1,100,101,99,100,1,2,100]]
    client._get=get
    assert asyncio.run(client.get_klines('BTCUSDT'))==[]


def test_missing_binance_history_is_hard_blocked(tmp_path):
    runner=GridSignalRunner(Settings(output_dir=tmp_path,dry_run=True),FakeMarketDataProvider(),FakeNotifier())
    rows=asyncio.run(runner.market_data_provider.fetch_candidates(1));rows[0].binance_candles_15m=[]
    score=runner.scorer.score(rows[0])
    assert score.hard_blocked and 'execution_data_missing' in score.risk_tags


def test_invalid_current_proposal_is_rejected_even_when_past_range_is_valid():
    result=simulate_grid(candles([100]*30),6,3,500,bound_atr=1000)
    assert result.score==0 and 'invalid_range' in result.tags


def test_cross_venue_price_basis_is_hard_blocked(tmp_path):
    runner=GridSignalRunner(Settings(output_dir=tmp_path,dry_run=True),FakeMarketDataProvider(),FakeNotifier())
    rows=asyncio.run(runner.market_data_provider.fetch_candidates(1))
    rows[0].binance_ticker=replace(rows[0].binance_ticker,price=rows[0].okx_ticker.price*1.02)
    score=runner.scorer.score(rows[0])
    assert score.hard_blocked and 'execution_price_basis' in score.risk_tags
