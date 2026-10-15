from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Action = Literal["buy", "sell", "hold"]


class Decision(BaseModel):
	"""What the decision provider (LLM or rules) returns. Validated before use."""

	action: Action
	confidence: float = Field(ge=0.0, le=1.0)
	reasoning: str = Field(max_length=1000)


class MarketSnapshot(BaseModel):
	symbol: str
	timeframe: str
	timestamp: datetime  # open time of the last *closed* candle (UTC)
	price: float
	sma_fast: float
	sma_slow: float
	rsi: float
	atr_pct: float
	change_24h_pct: float
	range_high: float
	range_low: float


class Position(BaseModel):
	symbol: str
	qty: float = 0.0
	entry_price: float = 0.0  # cost basis per unit, fees included

	@property
	def is_flat(self) -> bool:
		return self.qty <= 0


class Verdict(BaseModel):
	"""Risk manager output: the only thing the executor ever acts on."""

	action: Action
	quote_amount: float = 0.0
	reason: str


class Fill(BaseModel):
	symbol: str
	side: Literal["buy", "sell"]
	qty: float
	price: float
	fee: float  # in quote currency
	net_quote: float  # buy: total spent, sell: total received after fee
	paper: bool
