"""resale-roi-calculator FastAPI service.

Endpoints:
  GET  /health             liveness (no auth)
  GET  /v1/me              plan + usage for the presented key
  POST /v1/roi             ROI breakdown for a resale deal
  POST /v1/scan            under/overvalue verdict for an asking price
Auth: `Authorization: Bearer <api-key>` or `X-API-Key: <api-key>`.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import auth
from .calc import DealInput, ROIResult, compute_roi, scan_deal

@asynccontextmanager
async def _lifespan(_app: FastAPI):
    auth.init_db()
    yield


app = FastAPI(
    title="resale-roi-calculator",
    version="1.0.0",
    description=(
        "ROI breakdown and under/overvalue verdicts for resale deals "
        "(FB Marketplace / Kijiji style flips). Auth via API key."
    ),
)
app.router.lifespan_context = _lifespan


class DealRequest(BaseModel):
    buy_price: float = Field(gt=0, description="Purchase / asking price")
    sell_price: float = Field(gt=0, description="Expected resale price")
    platform_fee_pct: float = Field(default=0.0, ge=0, le=100)
    fixed_fee: float = Field(default=0.0, ge=0)
    shipping_cost: float = Field(default=0.0, ge=0)
    other_costs: float = Field(default=0.0, ge=0)
    hold_days: int = Field(default=0, ge=0, description="Days between buy and sell")


class ScanRequest(BaseModel):
    asking_price: float = Field(gt=0)
    expected_resale_price: float = Field(gt=0)
    platform_fee_pct: float = Field(default=0.0, ge=0, le=100)
    fixed_fee: float = Field(default=0.0, ge=0)
    shipping_cost: float = Field(default=0.0, ge=0)
    other_costs: float = Field(default=0.0, ge=0)
    hold_days: int = Field(default=0, ge=0)


class ROIResponse(BaseModel):
    total_cost: float
    net_profit: float
    roi_pct: float
    annualized_roi_pct: float | None
    break_even_sell_price: float
    verdict: str


class ScanResponse(ROIResponse):
    market_verdict: str  # undervalued | fair | overvalued


def _require_key(
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header()] = None,
) -> auth.KeyInfo:
    key = x_api_key
    if not key and authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer":
            key = token.strip()
    if not key:
        raise HTTPException(status_code=401, detail="missing API key")
    info = auth.lookup_key(key)
    if info is None:
        raise HTTPException(status_code=401, detail="invalid API key")
    return info


def _enforce(info: auth.KeyInfo) -> None:
    state = auth.consume(info.key, info.plan)
    if state.limited:
        headers = {"Retry-After": str(state.retry_after_seconds)}
        if state.reason == "daily":
            detail = f"daily cap reached for plan '{state.plan}' ({state.daily_cap}/day)"
        else:
            detail = f"rate limit reached for plan '{state.plan}'"
        raise HTTPException(
            status_code=429, detail=detail, headers=headers
        )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/v1/me")
def me(info: auth.KeyInfo = Depends(_require_key)) -> dict:
    state = auth.peek(info.key, info.plan)
    return {
        "plan": info.plan,
        "label": info.label,
        "used_today": state.used_today,
        "daily_cap": state.daily_cap,
        "requests_per_minute": auth.PER_MINUTE_CAPS[info.plan],
    }


@app.post("/v1/roi", response_model=ROIResponse)
def roi(
    req: DealRequest, info: auth.KeyInfo = Depends(_require_key)
) -> ROIResult:
    _enforce(info)
    return compute_roi(
        DealInput(
            buy_price=req.buy_price,
            sell_price=req.sell_price,
            platform_fee_pct=req.platform_fee_pct,
            fixed_fee=req.fixed_fee,
            shipping_cost=req.shipping_cost,
            other_costs=req.other_costs,
            hold_days=req.hold_days,
        )
    )


@app.post("/v1/scan", response_model=ScanResponse)
def scan(req: ScanRequest, info: auth.KeyInfo = Depends(_require_key)) -> dict:
    _enforce(info)
    result, market_verdict = scan_deal(
        DealInput(
            buy_price=req.asking_price,
            sell_price=req.expected_resale_price,
            platform_fee_pct=req.platform_fee_pct,
            fixed_fee=req.fixed_fee,
            shipping_cost=req.shipping_cost,
            other_costs=req.other_costs,
            hold_days=req.hold_days,
        )
    )
    return {**result.__dict__, "market_verdict": market_verdict}


@app.exception_handler(HTTPException)
async def _http_exc_handler(_request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers
    )


def run() -> None:
    import uvicorn

    host = os.environ.get("ROI_HOST", "127.0.0.1")
    port = int(os.environ.get("ROI_PORT", "8101"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run()
