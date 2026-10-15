from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import anthropic
from anthropic.types import ToolParam

from bot.models import Decision, MarketSnapshot, Position

SYSTEM_PROMPT = (
	"You are a cautious crypto spot-trading analyst. You receive a compact market snapshot and "
	"the current position. Decide buy, sell or hold. The account is long-only spot: 'buy' opens "
	"a position when flat, 'sell' closes it. Prefer hold when signals are mixed. Confidence must "
	"reflect real uncertainty; most situations deserve well under 0.6. Keep reasoning to a few "
	"sentences. You cannot know the future; do not claim to."
)

DECISION_TOOL: ToolParam = {
	"name": "submit_decision",
	"description": "Submit the trading decision for this candle.",
	"input_schema": Decision.model_json_schema(),
}


@dataclass(frozen=True)
class ProviderResult:
	decision: Decision
	prompt: str | None = None  # logged for later evaluation
	raw: str | None = None


class DecisionProvider(Protocol):
	name: str

	def decide(self, snapshot: MarketSnapshot, position: Position) -> ProviderResult: ...


def build_prompt(s: MarketSnapshot, p: Position) -> str:
	if p.is_flat:
		pos = "flat (no position)"
	else:
		pnl = (s.price / p.entry_price - 1) * 100
		pos = f"long {p.qty:.6f} @ {p.entry_price:.2f} (unrealized {pnl:+.2f}%)"
	trend = "above" if s.sma_fast > s.sma_slow else "below"
	return (
		f"{s.symbol}, {s.timeframe} candles, last closed candle "
		f"{s.timestamp:%Y-%m-%d %H:%M} UTC\n"
		f"Price: {s.price:.2f}\n"
		f"24h change: {s.change_24h_pct:+.2f}%\n"
		f"SMA20 {s.sma_fast:.2f} is {trend} SMA50 {s.sma_slow:.2f}\n"
		f"RSI(14): {s.rsi:.1f}\n"
		f"ATR(14) as % of price: {s.atr_pct:.2f}%\n"
		f"Last 50 candles range: {s.range_low:.2f} - {s.range_high:.2f}\n"
		f"Current position: {pos}\n"
	)


class ClaudeProvider:
	def __init__(self, model: str, api_key: str | None = None) -> None:
		self.name = model
		self._client = anthropic.Anthropic(api_key=api_key)

	def decide(self, snapshot: MarketSnapshot, position: Position) -> ProviderResult:
		prompt = build_prompt(snapshot, position)
		resp = self._client.messages.create(
			model=self.name,
			max_tokens=600,
			system=SYSTEM_PROMPT,
			tools=[DECISION_TOOL],
			tool_choice={"type": "tool", "name": "submit_decision"},
			messages=[{"role": "user", "content": prompt}],
		)
		for block in resp.content:
			if block.type == "tool_use":
				decision = Decision.model_validate(block.input)
				return ProviderResult(decision, prompt, str(block.input))
		raise ValueError("Model returned no tool_use block")


class BaselineProvider:
	"""Plain SMA-crossover + RSI rules. Run it alongside Claude to see if the LLM adds anything."""

	name = "baseline-sma"

	def decide(self, snapshot: MarketSnapshot, position: Position) -> ProviderResult:
		if snapshot.sma_fast > snapshot.sma_slow and snapshot.rsi < 70:
			d = Decision(action="buy", confidence=0.7, reasoning="Uptrend, RSI not overbought")
		elif snapshot.sma_fast < snapshot.sma_slow:
			d = Decision(action="sell", confidence=0.7, reasoning="Downtrend")
		else:
			d = Decision(action="hold", confidence=1.0, reasoning="No clear signal")
		return ProviderResult(d)
