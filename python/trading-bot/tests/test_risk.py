from datetime import UTC, datetime
from pathlib import Path

from aibot.models import Decision, MarketSnapshot, Position
from aibot.risk import RiskLimits, RiskManager


def snap(price: float = 100.0) -> MarketSnapshot:
    return MarketSnapshot(
        symbol="BTC/USDT",
        timeframe="1h",
        timestamp=datetime.now(UTC),
        price=price,
        sma_fast=1,
        sma_slow=1,
        rsi=50,
        atr_pct=1,
        change_24h_pct=0,
        range_high=110,
        range_low=90,
    )


def manager(tmp_path: Path) -> RiskManager:
    return RiskManager(RiskLimits(50, 3, 20, 0.6, str(tmp_path / "KILL")))


def dec(action: str, conf: float = 0.9) -> Decision:
    return Decision(action=action, confidence=conf, reasoning="t")  # type: ignore[arg-type]


def test_low_confidence_is_vetoed(tmp_path: Path) -> None:
    v = manager(tmp_path).review(dec("buy", 0.3), snap(), Position(symbol="BTC/USDT"), 0)
    assert v.action == "hold"


def test_buy_when_flat_is_approved(tmp_path: Path) -> None:
    v = manager(tmp_path).review(dec("buy"), snap(), Position(symbol="BTC/USDT"), 0)
    assert v.action == "buy" and v.quote_amount == 50


def test_stop_loss_overrides_model(tmp_path: Path) -> None:
    pos = Position(symbol="BTC/USDT", qty=1, entry_price=100)
    v = manager(tmp_path).review(dec("hold"), snap(96.0), pos, 0)
    assert v.action == "sell"


def test_daily_loss_limit_halts_buys(tmp_path: Path) -> None:
    v = manager(tmp_path).review(dec("buy"), snap(), Position(symbol="BTC/USDT"), -25)
    assert v.action == "hold"


def test_kill_switch(tmp_path: Path) -> None:
    (tmp_path / "KILL").touch()
    v = manager(tmp_path).review(dec("buy"), snap(), Position(symbol="BTC/USDT"), 0)
    assert v.action == "hold"
