from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal, cast

from dotenv import load_dotenv

Mode = Literal["paper", "testnet", "live"]


@dataclass(frozen=True)
class Settings:
    mode: Mode
    provider: str
    claude_model: str
    symbol: str
    timeframe: str
    poll_seconds: int
    trade_size_usdt: float
    stop_loss_pct: float
    max_daily_loss_usdt: float
    min_confidence: float
    fee_rate: float
    binance_key: str
    binance_secret: str
    db_path: str
    kill_file: str

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv()
        mode = os.getenv("MODE", "paper")
        if mode not in ("paper", "testnet", "live"):
            raise ValueError(f"MODE must be paper, testnet or live (got {mode!r})")
        if mode == "live" and os.getenv("CONFIRM_LIVE") != "yes":
            raise SystemExit("Refusing to run live: set CONFIRM_LIVE=yes to confirm.")
        return cls(
            mode=cast(Mode, mode),
            provider=os.getenv("PROVIDER", "claude"),
            claude_model=os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5"),
            symbol=os.getenv("SYMBOL", "BTC/USDT"),
            timeframe=os.getenv("TIMEFRAME", "1h"),
            poll_seconds=int(os.getenv("POLL_SECONDS", "300")),
            trade_size_usdt=float(os.getenv("TRADE_SIZE_USDT", "50")),
            stop_loss_pct=float(os.getenv("STOP_LOSS_PCT", "3")),
            max_daily_loss_usdt=float(os.getenv("MAX_DAILY_LOSS_USDT", "20")),
            min_confidence=float(os.getenv("MIN_CONFIDENCE", "0.6")),
            fee_rate=float(os.getenv("FEE_RATE", "0.001")),
            binance_key=os.getenv("BINANCE_API_KEY", ""),
            binance_secret=os.getenv("BINANCE_API_SECRET", ""),
            db_path=os.getenv("DB_PATH", "aibot.db"),
            kill_file=os.getenv("KILL_FILE", "KILL"),
        )
