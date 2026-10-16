from app.calc import DealInput, compute_roi, scan_deal


def test_simple_profit():
    r = compute_roi(DealInput(buy_price=100, sell_price=150))
    assert r.total_cost == 100
    assert r.net_profit == 50
    assert r.roi_pct == 50.0
    assert r.verdict == "strong"


def test_platform_fee_and_costs():
    r = compute_roi(
        DealInput(
            buy_price=100,
            sell_price=150,
            platform_fee_pct=10.0,
            fixed_fee=5,
            shipping_cost=10,
            other_costs=5,
        )
    )
    # total_cost = 100 + 5 + 10 + 5 = 120; fee = 15; profit = 150 - 15 - 120 = 15
    assert r.total_cost == 120
    assert r.net_profit == 15
    assert r.roi_pct == 12.5
    assert r.verdict == "acceptable"


def test_loss_verdict():
    r = compute_roi(DealInput(buy_price=100, sell_price=80))
    assert r.net_profit == -20
    assert r.roi_pct == -20.0
    assert r.verdict == "loss"


def test_thin_verdict():
    r = compute_roi(DealInput(buy_price=100, sell_price=105))
    assert r.net_profit == 5
    assert r.verdict == "thin"


def test_annualized_roi():
    r = compute_roi(DealInput(buy_price=100, sell_price=110, hold_days=30))
    assert r.roi_pct == 10.0
    assert r.annualized_roi_pct == 121.67  # 10 * 365/30 rounded


def test_no_hold_days_no_annualized():
    r = compute_roi(DealInput(buy_price=100, sell_price=110))
    assert r.annualized_roi_pct is None


def test_break_even():
    r = compute_roi(
        DealInput(buy_price=100, sell_price=150, platform_fee_pct=10.0)
    )
    # break-even s: s*0.9 = 100 -> 111.11
    assert r.break_even_sell_price == 111.11


def test_scan_undervalued():
    _, v = scan_deal(DealInput(buy_price=100, sell_price=130))
    assert v == "undervalued"


def test_scan_fair():
    _, v = scan_deal(DealInput(buy_price=100, sell_price=110))
    assert v == "fair"


def test_scan_overvalued():
    _, v = scan_deal(DealInput(buy_price=100, sell_price=102))
    assert v == "overvalued"
