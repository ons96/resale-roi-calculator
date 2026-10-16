"""Pure resale-ROI computation. No I/O; fully unit-testable."""

from __future__ import annotations

from dataclasses import dataclass

# Verdict thresholds (percent ROI on total cost).
STRONG_ROI_PCT = 30.0
ACCEPTABLE_ROI_PCT = 10.0
# Scan thresholds: asking price vs expected resale value.
UNDERVALUED_ROI_PCT = 20.0
FAIR_ROI_PCT = 5.0


@dataclass(frozen=True)
class DealInput:
    """A resale deal. All money fields in the same currency (caller's choice)."""

    buy_price: float
    sell_price: float
    platform_fee_pct: float = 0.0
    fixed_fee: float = 0.0
    shipping_cost: float = 0.0
    other_costs: float = 0.0
    hold_days: int = 0


@dataclass(frozen=True)
class ROIResult:
    total_cost: float
    net_profit: float
    roi_pct: float
    annualized_roi_pct: float | None
    break_even_sell_price: float
    verdict: str


def compute_roi(deal: DealInput) -> ROIResult:
    """Compute profit, ROI, break-even and a verdict for a resale deal.

    ROI is net profit divided by total out-of-pocket cost (buy price plus all
    fees and costs), expressed as a percentage. Annualized ROI compounds the
    hold period to a 365-day basis and is None when hold_days is zero.
    """
    total_cost = (
        deal.buy_price
        + deal.fixed_fee
        + deal.shipping_cost
        + deal.other_costs
    )
    platform_fee = deal.sell_price * (deal.platform_fee_pct / 100.0)
    net_profit = deal.sell_price - platform_fee - total_cost

    roi_pct = (net_profit / total_cost) * 100.0 if total_cost > 0 else 0.0

    annualized: float | None = None
    if deal.hold_days > 0 and total_cost > 0:
        annualized = roi_pct * (365.0 / deal.hold_days)

    # Break-even: sell price s where s - s*fee_pct - fixed - shipping - other - buy = 0
    fee_factor = 1.0 - deal.platform_fee_pct / 100.0
    if fee_factor > 0:
        break_even = (total_cost) / fee_factor
    else:
        break_even = float("inf")

    if roi_pct >= STRONG_ROI_PCT:
        verdict = "strong"
    elif roi_pct >= ACCEPTABLE_ROI_PCT:
        verdict = "acceptable"
    elif net_profit > 0:
        verdict = "thin"
    else:
        verdict = "loss"

    return ROIResult(
        total_cost=round(total_cost, 2),
        net_profit=round(net_profit, 2),
        roi_pct=round(roi_pct, 2),
        annualized_roi_pct=round(annualized, 2) if annualized is not None else None,
        break_even_sell_price=round(break_even, 2),
        verdict=verdict,
    )


def scan_deal(deal: DealInput) -> tuple[ROIResult, str]:
    """Under/overvalue scan: is the asking price good relative to expected resale?

    Returns the ROI result plus a market verdict:
      undervalued -- ROI >= 20%  (buy candidate)
      fair        -- ROI >= 5%
      overvalued  -- ROI < 5%    (walk away)
    """
    result = compute_roi(deal)
    if result.roi_pct >= UNDERVALUED_ROI_PCT:
        market_verdict = "undervalued"
    elif result.roi_pct >= FAIR_ROI_PCT:
        market_verdict = "fair"
    else:
        market_verdict = "overvalued"
    return result, market_verdict
