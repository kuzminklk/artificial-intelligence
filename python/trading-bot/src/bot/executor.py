from __future__ import annotations

from typing import Any, Protocol

from bot.models import Fill


class Executor(Protocol):
	def buy(self, symbol: str, quote_amount: float, price: float) -> Fill: ...

	def sell(self, symbol: str, qty: float, price: float) -> Fill: ...


class PaperExecutor:
	"""Simulated market orders: fee plus a small slippage against you."""

	def __init__(self, fee_rate: float, slippage_bps: float = 5.0) -> None:
		self.fee_rate = fee_rate
		self.slip = slippage_bps / 10_000

	def buy(self, symbol: str, quote_amount: float, price: float) -> Fill:
		px = price * (1 + self.slip)
		fee = quote_amount * self.fee_rate
		qty = (quote_amount - fee) / px
		return Fill(
			symbol=symbol,
			side="buy",
			qty=qty,
			price=px,
			fee=fee,
			net_quote=quote_amount,
			paper=True,
		)

	def sell(self, symbol: str, qty: float, price: float) -> Fill:
		px = price * (1 - self.slip)
		gross = qty * px
		fee = gross * self.fee_rate
		return Fill(
			symbol=symbol,
			side="sell",
			qty=qty,
			price=px,
			fee=fee,
			net_quote=gross - fee,
			paper=True,
		)


class LiveExecutor:
	"""Real market orders through ccxt (testnet or live, depending on the exchange object)."""

	def __init__(self, exchange: Any, fee_rate: float, paper: bool = False) -> None:
		self.ex = exchange
		self.fee_rate = fee_rate
		self.paper = paper

	def buy(self, symbol: str, quote_amount: float, price: float) -> Fill:
		order = self.ex.create_market_buy_order_with_cost(symbol, quote_amount)
		filled = float(order["filled"])
		avg = float(order.get("average") or price)
		cost = float(order.get("cost") or filled * avg)
		fee = cost * self.fee_rate
		# Binance usually takes the fee from the received asset, so net qty is slightly lower.
		# This is an estimate: reconcile against fetch_balance() if you need exact accounting.
		return Fill(
			symbol=symbol,
			side="buy",
			qty=filled * (1 - self.fee_rate),
			price=avg,
			fee=fee,
			net_quote=cost,
			paper=self.paper,
		)

	def sell(self, symbol: str, qty: float, price: float) -> Fill:
		base = symbol.split("/")[0]
		free = float(self.ex.fetch_balance()["free"].get(base, 0.0))
		amount = float(self.ex.amount_to_precision(symbol, min(qty, free)))
		order = self.ex.create_market_sell_order(symbol, amount)
		avg = float(order.get("average") or price)
		gross = float(order.get("cost") or amount * avg)
		fee = gross * self.fee_rate
		return Fill(
			symbol=symbol,
			side="sell",
			qty=amount,
			price=avg,
			fee=fee,
			net_quote=gross - fee,
			paper=self.paper,
		)
