# NOFX Compatibility Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make NeuralGridSignal generate grid strategies that are less likely to be rejected by nofx runtime AI without modifying the installed nofx container.

**Architecture:** NeuralGridSignal will compute a nofx-oriented preflight from 5m candles, apply hard/soft scoring penalties that mirror nofx grid prompt thresholds, and export explicit grid bounds instead of relying on nofx ATR auto bounds. Reports and Telegram messages will show the nofx compatibility verdict.

**Tech Stack:** Python dataclasses, existing indicator helpers, pytest, existing markdown/Telegram renderers.

---

### Task 1: Data Model And Tests

**Files:**
- Modify: `neural_grid_signal/models.py`
- Test: `tests/test_scoring.py`, `tests/test_strategy.py`

- [ ] Add 5m OKX candles and nofx preflight fields to the market/score models.
- [ ] Add tests showing an ONDO-like 5m wide-Bollinger trend is blocked or heavily penalized.
- [ ] Add tests showing generated JSON uses explicit bounds.

### Task 2: Market Data And Scoring

**Files:**
- Modify: `neural_grid_signal/market_data.py`
- Modify: `neural_grid_signal/scoring.py`

- [ ] Fetch OKX 5m candles alongside existing 15m/1h/4h data.
- [ ] Compute nofx preflight metrics: 5m Bollinger width, 5m ATR%, RSI14, Bollinger position, 1h/4h change, grid spacing display risk.
- [ ] Apply nofx risk tags and cap/penalize final score when runtime conditions violate nofx grid prompt rules.

### Task 3: Strategy Export

**Files:**
- Modify: `neural_grid_signal/strategy.py`
- Modify: `neural_grid_signal/backtest.py` if spacing search needs constraints.

- [ ] Export `use_atr_bounds=false`.
- [ ] Write computed `lower_price` and `upper_price` into JSON.
- [ ] Avoid grid configurations whose visible nofx spacing would render as `$0.00`.

### Task 4: Reporting And Docs

**Files:**
- Modify: `neural_grid_signal/runner.py`
- Modify: `neural_grid_signal/notifier.py`
- Modify: docs as needed.

- [ ] Include nofx preflight metrics in markdown report.
- [ ] Include the verdict and explicit-bounds mode in Telegram notification.
- [ ] Document that fixed bounds are used to avoid nofx container ATR-bound fallback.

### Task 5: Verification

**Commands:**
- `venv/bin/python -m pytest -q`
- `venv/bin/python -m compileall neural_grid_signal tests`

- [ ] Confirm tests pass.
- [ ] Inspect a generated strategy/report if public API access is available.
