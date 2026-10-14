# aibot: experimental LLM trading bot (Binance + Claude)

The LLM is a **signal generator**. Plain code (the risk manager) decides whether anything gets traded.

```
Binance (ccxt) -> data.py -> llm.py (Claude, tool-use JSON) -> risk.py -> executor.py -> Binance
                                                      every decision/fill logged to SQLite
```

## Setup

```bash
uv sync
cp .env.example .env     # add ANTHROPIC_API_KEY
uv run aibot --once      # one paper-trading step
uv run aibot             # loop (Ctrl+C to stop)
```

Dev checks: `uv run ruff check . && uv run mypy src && uv run pytest`

## Modes

| MODE | Data | Orders | Keys needed |
|------|------|--------|-------------|
| `paper` (default) | real Binance prices | simulated locally (fee + slippage) | Anthropic only |
| `testnet` | Binance spot testnet | real testnet orders | testnet keys (testnet.binance.vision) |
| `live` | Binance | real money | trade-only keys + `CONFIRM_LIVE=yes` |

## Safety

- Create Binance API keys with **trading only, no withdrawals**, and IP-restrict them.
- `touch KILL` stops all new trades (stop-loss exits still fire).
- Limits live in `.env`: trade size, stop-loss %, max daily loss, min confidence.
- Long-only spot, one position at a time. Intentionally simple.
- Paper trade for weeks before considering real money.

## Experiments

- Run `PROVIDER=baseline DB_PATH=baseline.db` next to `PROVIDER=claude DB_PATH=claude.db` and compare.
- Compare models by changing `CLAUDE_MODEL`, with one DB per model.
- Edit `build_prompt()` / `SYSTEM_PROMPT` in `llm.py`; add news/sentiment as extra inputs.
- Query the `decisions` and `fills` tables in `aibot.db` to evaluate (prompt, response, verdict, pnl).

## Known limitations

- Live fill accounting is approximate (Binance often takes fees from the received asset).
- Position state is stored locally, not reconciled with the exchange balance.
- No backtester yet. LLM backtests are also prone to lookahead contamination, so prefer forward paper trading.
