from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd

from bot.models import MarketSnapshot

FAST, SLOW, RSI_PERIOD, ATR_PERIOD, RANGE_BARS = 20, 50, 14, 14, 50


def _rsi(close: pd.Series) -> pd.Series:
	delta = close.diff()
	gain = delta.clip(lower=0).ewm(alpha=1 / RSI_PERIOD, adjust=False).mean()
	loss = (-delta.clip(upper=0)).ewm(alpha=1 / RSI_PERIOD, adjust=False).mean()
	rsi = 100 - 100 / (1 + gain / loss)
	return rsi.fillna(50.0)


def _atr_pct(df: pd.DataFrame) -> pd.Series:
	prev_close = df["close"].shift(1)
	tr = pd.concat(
		[
			df["high"] - df["low"],
			(df["high"] - prev_close).abs(),
			(df["low"] - prev_close).abs(),
		],
		axis=1,
	).max(axis=1)
	return tr.ewm(alpha=1 / ATR_PERIOD, adjust=False).mean() / df["close"] * 100


def fetch_snapshot(exchange: Any, symbol: str, timeframe: str, limit: int = 200) -> MarketSnapshot:
	raw = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
	df = pd.DataFrame(raw, columns=["ts", "open", "high", "low", "close", "volume"])
	df = df.iloc[:-1].reset_index(drop=True)  # drop the still-forming candle
	if len(df) < SLOW + 1:
		raise RuntimeError(f"Not enough candles ({len(df)}) to compute indicators")

	close = df["close"]
	bars_per_day = max(1, 86400 // int(exchange.parse_timeframe(timeframe)))
	last = df.iloc[-1]
	window = df.iloc[-RANGE_BARS:]

	return MarketSnapshot(
		symbol=symbol,
		timeframe=timeframe,
		timestamp=datetime.fromtimestamp(int(last["ts"]) / 1000, tz=UTC),
		price=float(last["close"]),
		sma_fast=float(close.rolling(FAST).mean().iloc[-1]),
		sma_slow=float(close.rolling(SLOW).mean().iloc[-1]),
		rsi=float(_rsi(close).iloc[-1]),
		atr_pct=float(_atr_pct(df).iloc[-1]),
		change_24h_pct=float((close.iloc[-1] / close.iloc[-1 - bars_per_day] - 1) * 100),
		range_high=float(window["high"].max()),
		range_low=float(window["low"].min()),
	)
