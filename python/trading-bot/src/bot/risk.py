from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bot.models import Decision, MarketSnapshot, Position, Verdict


@dataclass(frozen=True)
class RiskLimits:
	trade_size_usdt: float
	stop_loss_pct: float
	max_daily_loss_usdt: float
	min_confidence: float
	kill_file: str


class RiskManager:
	"""Deterministic gatekeeper. The LLM can suggest, only this class can approve."""

	def __init__(self, limits: RiskLimits) -> None:
		self.limits = limits

	def review(
		self,
		decision: Decision,
		snapshot: MarketSnapshot,
		position: Position,
		daily_pnl: float,
	) -> Verdict:
		lim = self.limits

		if Path(lim.kill_file).exists():
			return Verdict(action="hold", reason="kill switch file present")

		# Stop-loss is enforced regardless of what the model says.
		if not position.is_flat:
			stop = position.entry_price * (1 - lim.stop_loss_pct / 100)
			if snapshot.price <= stop:
				return Verdict(action="sell", reason=f"stop-loss hit ({stop:.2f})")

		if daily_pnl <= -lim.max_daily_loss_usdt:
			return Verdict(action="hold", reason=f"daily loss limit reached ({daily_pnl:.2f})")

		if decision.action == "hold":
			return Verdict(action="hold", reason="model says hold")
		if decision.confidence < lim.min_confidence:
			return Verdict(action="hold", reason=f"confidence {decision.confidence:.2f} too low")

		if decision.action == "buy":
			if not position.is_flat:
				return Verdict(action="hold", reason="already long")
			return Verdict(action="buy", quote_amount=lim.trade_size_usdt, reason="approved")

		if position.is_flat:
			return Verdict(action="hold", reason="nothing to sell")
		return Verdict(action="sell", reason="approved")
