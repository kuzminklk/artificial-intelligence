from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from bot.models import Decision, Fill, MarketSnapshot, Position, Verdict

SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY, ts TEXT, candle_ts TEXT, symbol TEXT, provider TEXT,
    snapshot TEXT, prompt TEXT, raw TEXT, decision TEXT, verdict TEXT
);
CREATE TABLE IF NOT EXISTS fills (
    id INTEGER PRIMARY KEY, ts TEXT, symbol TEXT, side TEXT, qty REAL, price REAL,
    fee REAL, net_quote REAL, pnl REAL, paper INTEGER
);
CREATE TABLE IF NOT EXISTS position (
    symbol TEXT PRIMARY KEY, qty REAL, entry_price REAL
);
"""


def _now() -> str:
	return datetime.now(UTC).isoformat()


class Store:
	def __init__(self, path: str) -> None:
		self._db = sqlite3.connect(path)
		self._db.executescript(SCHEMA)

	def log_decision(
		self,
		provider: str,
		snapshot: MarketSnapshot,
		prompt: str | None,
		raw: str | None,
		decision: Decision,
		verdict: Verdict,
	) -> None:
		self._db.execute(
			"INSERT INTO decisions (ts, candle_ts, symbol, provider, snapshot, prompt, raw,"
			" decision, verdict) VALUES (?,?,?,?,?,?,?,?,?)",
			(
				_now(),
				snapshot.timestamp.isoformat(),
				snapshot.symbol,
				provider,
				snapshot.model_dump_json(),
				prompt,
				raw,
				decision.model_dump_json(),
				verdict.model_dump_json(),
			),
		)
		self._db.commit()

	def last_candle_ts(self, symbol: str) -> datetime | None:
		row = self._db.execute(
			"SELECT candle_ts FROM decisions WHERE symbol=? ORDER BY id DESC LIMIT 1", (symbol,)
		).fetchone()
		return datetime.fromisoformat(row[0]) if row else None

	def log_fill(self, fill: Fill, pnl: float) -> None:
		self._db.execute(
			"INSERT INTO fills (ts, symbol, side, qty, price, fee, net_quote, pnl, paper) VALUES (?,?,?,?,?,?,?,?,?)",
			(
				_now(),
				fill.symbol,
				fill.side,
				fill.qty,
				fill.price,
				fill.fee,
				fill.net_quote,
				pnl,
				int(fill.paper),
			),
		)
		self._db.commit()

	def get_position(self, symbol: str) -> Position:
		row = self._db.execute("SELECT qty, entry_price FROM position WHERE symbol=?", (symbol,)).fetchone()
		if row is None:
			return Position(symbol=symbol)
		return Position(symbol=symbol, qty=row[0], entry_price=row[1])

	def set_position(self, pos: Position) -> None:
		self._db.execute(
			"INSERT INTO position (symbol, qty, entry_price) VALUES (?,?,?)"
			" ON CONFLICT(symbol) DO UPDATE SET qty=excluded.qty, entry_price=excluded.entry_price",
			(pos.symbol, pos.qty, pos.entry_price),
		)
		self._db.commit()

	def daily_realized_pnl(self) -> float:
		today = datetime.now(UTC).strftime("%Y-%m-%d")
		row = self._db.execute(
			"SELECT COALESCE(SUM(pnl), 0) FROM fills WHERE substr(ts, 1, 10) = ?", (today,)
		).fetchone()
		return float(row[0])
