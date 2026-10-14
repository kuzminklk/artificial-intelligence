from __future__ import annotations

import argparse
import logging
import os
import time
from datetime import datetime
from typing import Any

import ccxt

from bot.config import Settings
from bot.data import fetch_snapshot
from bot.executor import Executor, LiveExecutor, PaperExecutor
from bot.llm import BaselineProvider, ClaudeProvider, DecisionProvider, ProviderResult
from bot.models import Decision, Position, Verdict
from bot.risk import RiskLimits, RiskManager
from bot.store import Store

log = logging.getLogger("aibot")


def make_exchange(s: Settings) -> Any:
    params: dict[str, Any] = {"enableRateLimit": True, "options": {"defaultType": "spot"}}
    if s.mode != "paper":
        params |= {"apiKey": s.binance_key, "secret": s.binance_secret}
    ex = ccxt.binance(params)
    if s.mode == "testnet":
        ex.set_sandbox_mode(True)
    ex.load_markets()
    return ex


def make_provider(s: Settings) -> DecisionProvider:
    if s.provider == "claude":
        return ClaudeProvider(s.claude_model, os.getenv("ANTHROPIC_API_KEY"))
    if s.provider == "baseline":
        return BaselineProvider()
    raise ValueError(f"Unknown PROVIDER {s.provider!r}")


class Bot:
    def __init__(
        self,
        settings: Settings,
        exchange: Any,
        provider: DecisionProvider,
        store: Store,
        risk: RiskManager,
        executor: Executor,
    ) -> None:
        self.s, self.ex, self.provider = settings, exchange, provider
        self.store, self.risk, self.executor = store, risk, executor
        self._last_candle: datetime | None = store.last_candle_ts(settings.symbol)

    def step(self) -> None:
        snap = fetch_snapshot(self.ex, self.s.symbol, self.s.timeframe)
        if snap.timestamp == self._last_candle:
            log.debug("No new closed candle yet")
            return
        self._last_candle = snap.timestamp

        position = self.store.get_position(self.s.symbol)
        try:
            result = self.provider.decide(snap, position)
        except Exception:
            log.exception("Provider failed; defaulting to hold")
            result = ProviderResult(
                Decision(action="hold", confidence=0.0, reasoning="provider error")
            )

        verdict = self.risk.review(result.decision, snap, position, self.store.daily_realized_pnl())
        log.info(
            "%s price=%.2f model=%s(%.2f) -> %s (%s)",
            snap.symbol,
            snap.price,
            result.decision.action,
            result.decision.confidence,
            verdict.action,
            verdict.reason,
        )
        self._execute(verdict, snap.price, position)
        self.store.log_decision(
            self.provider.name, snap, result.prompt, result.raw, result.decision, verdict
        )

    def _execute(self, verdict: Verdict, price: float, position: Position) -> None:
        sym = self.s.symbol
        if verdict.action == "buy":
            fill = self.executor.buy(sym, verdict.quote_amount, price)
            self.store.set_position(
                Position(symbol=sym, qty=fill.qty, entry_price=fill.net_quote / fill.qty)
            )
            self.store.log_fill(fill, pnl=0.0)
            log.info("BUY  %.6f @ %.2f", fill.qty, fill.price)
        elif verdict.action == "sell":
            fill = self.executor.sell(sym, position.qty, price)
            pnl = fill.net_quote - position.qty * position.entry_price
            self.store.set_position(Position(symbol=sym))
            self.store.log_fill(fill, pnl=pnl)
            log.info("SELL %.6f @ %.2f (pnl %+.2f)", fill.qty, fill.price, pnl)


def main() -> None:
    parser = argparse.ArgumentParser(description="Experimental LLM trading bot")
    parser.add_argument("--once", action="store_true", help="run a single step and exit")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    s = Settings.from_env()
    log.info("mode=%s provider=%s symbol=%s tf=%s", s.mode, s.provider, s.symbol, s.timeframe)

    exchange = make_exchange(s)
    executor: Executor = (
        PaperExecutor(s.fee_rate) if s.mode == "paper" else LiveExecutor(exchange, s.fee_rate)
    )
    risk = RiskManager(
        RiskLimits(
            trade_size_usdt=s.trade_size_usdt,
            stop_loss_pct=s.stop_loss_pct,
            max_daily_loss_usdt=s.max_daily_loss_usdt,
            min_confidence=s.min_confidence,
            kill_file=s.kill_file,
        )
    )
    bot = Bot(s, exchange, make_provider(s), Store(s.db_path), risk, executor)

    while True:
        try:
            bot.step()
        except (ccxt.NetworkError, ccxt.ExchangeError):
            log.exception("Exchange error; will retry")
        if args.once:
            return
        try:
            time.sleep(s.poll_seconds)
        except KeyboardInterrupt:
            log.info("Stopped")
            return


if __name__ == "__main__":
    main()
