# resale-roi-calculator

FastAPI service that computes resale ROI and under/overvalue verdicts for
marketplace flips (FB Marketplace / Kijiji style). Built from the spec in
`SIX_WEEK_PLAN_2026-07.md` W2 #5.

## Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | no | liveness probe |
| GET | `/v1/me` | yes | plan, usage today, caps |
| POST | `/v1/roi` | yes | full ROI breakdown for a deal |
| POST | `/v1/scan` | yes | under/overvalue verdict for an asking price |
| GET | `/docs` | no | interactive OpenAPI docs |

Auth: `Authorization: Bearer <api-key>` or `X-API-Key: <api-key>`.

## Plans and usage caps

| Plan | Price | Requests/day | Requests/min |
|---|---|---|---|
| free | $0 | 100 | 10 |
| basic | $15/mo | 5,000 | 60 |
| pro | $49/mo | 50,000 | 300 |
| ultra | $199/mo | unlimited | 1,000 |

Exceeding a cap returns `429` with a `Retry-After` header (daily cap resets at
UTC midnight; rate limit resets each minute).

## Example

```bash
curl -s http://127.0.0.1:8101/v1/roi \
  -H "X-API-Key: roi_YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"buy_price": 100, "sell_price": 150, "platform_fee_pct": 10, "hold_days": 30}'
```

Response:

```json
{
  "total_cost": 100.0,
  "net_profit": 35.0,
  "roi_pct": 35.0,
  "annualized_roi_pct": 425.83,
  "break_even_sell_price": 111.11,
  "verdict": "strong"
}
```

`/v1/scan` takes `asking_price` + `expected_resale_price` and adds
`market_verdict`: `undervalued` (ROI >= 20%), `fair` (>= 5%), `overvalued`.

## Verdict thresholds

- `strong` ROI >= 30%
- `acceptable` ROI >= 10%
- `thin` profit > 0
- `loss` otherwise

## Local development

```bash
uv venv && uv pip install -e ".[dev]"
uv run pytest
uv run python -m app.main   # serves on 127.0.0.1:8101
```

Environment variables:

- `ROI_DB_PATH` — SQLite path for keys/usage (default `roi_usage.db`)
- `ROI_HOST` / `ROI_PORT` — bind address (default `127.0.0.1:8101`)

## API key management

Keys are created offline and inserted into the SQLite store (there is no
public signup endpoint by design):

```python
from app.auth import create_key
key = create_key("basic", label="customer-1")
```

## Deployment

See [DEPLOY.md](DEPLOY.md) for the VPS-40 systemd deployment guide.

## Scope / honesty notes

- This is a calculator, not market data. It does not fetch live resale prices;
  the caller supplies the expected resale value.
- Currency-agnostic: all money fields must be in the same currency.
- No warranty on ROI outcomes; thresholds are heuristics, not financial advice.
