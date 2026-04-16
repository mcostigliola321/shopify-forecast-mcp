"""Generate test fixture data for shopify-forecast-mcp.

Creates:
- tests/fixtures/sample_daily_revenue.csv (365 days, seasonal patterns)
- tests/fixtures/sample_orders.json (~100 orders, 3 products)
"""

import json
import random
from datetime import date, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
FIXTURES.mkdir(parents=True, exist_ok=True)

rng = np.random.default_rng(42)
random.seed(42)


# ---------------------------------------------------------------------------
# Part B: sample_daily_revenue.csv
# ---------------------------------------------------------------------------

def generate_revenue_csv() -> None:
    start = date(2025, 4, 1)
    days = 365
    rows = ["date,revenue"]

    # Promo windows (3-day bumps): random dates avoiding holidays
    promo_starts = [
        date(2025, 5, 15),
        date(2025, 9, 10),
        date(2026, 2, 5),
    ]
    promo_days = set()
    for ps in promo_starts:
        for d in range(3):
            promo_days.add(ps + timedelta(days=d))

    for i in range(days):
        d = start + timedelta(days=i)
        base = 4500.0

        # Weekly seasonality: weekends ~20% lower
        dow = d.weekday()
        if dow == 5:  # Saturday
            base *= 0.82
        elif dow == 6:  # Sunday
            base *= 0.78

        # Monthly mid-month uptick (days 13-17)
        if 13 <= d.day <= 17:
            base *= 1.06

        # Summer dip: June 15 - August 31
        if (d.month == 6 and d.day >= 15) or d.month == 7 or (d.month == 8 and d.day <= 31):
            base *= 0.85

        # Holiday spike: Black Friday week (late Nov)
        if d.month == 11 and 24 <= d.day <= 30:
            base *= 1.40

        # Holiday spike: mid-December
        if d.month == 12 and 10 <= d.day <= 23:
            base *= 1.30

        # Post-holiday dip: Jan 2-10
        if d.month == 1 and 2 <= d.day <= 10:
            base *= 0.90

        # Promo bumps (+25%)
        if d in promo_days:
            base *= 1.25

        # Random noise +/- 10%
        noise = rng.uniform(0.90, 1.10)
        revenue = round(base * noise, 2)

        rows.append(f"{d.isoformat()},{revenue}")

    (FIXTURES / "sample_daily_revenue.csv").write_text("\n".join(rows) + "\n")
    print(f"Wrote {len(rows) - 1} rows to sample_daily_revenue.csv")


# ---------------------------------------------------------------------------
# Part C: sample_orders.json
# ---------------------------------------------------------------------------

PRODUCTS = [
    {"product_id": "9001", "product_title": "Widget A", "sku": "WA-001", "price": 25.0},
    {"product_id": "9002", "product_title": "Gadget B", "sku": "GB-001", "price": 50.0},
    {"product_id": "9003", "product_title": "Premium C", "sku": "PC-001", "price": 150.0},
]


def make_line_item(li_id: int, product: dict, qty: int,
                   refund_qty: int = 0, refund_amt: float = 0.0) -> dict:
    gross = qty * product["price"]
    net_qty = qty - refund_qty
    net_rev = gross - refund_amt
    return {
        "id": str(li_id),
        "title": product["product_title"],
        "quantity": qty,
        "current_quantity": net_qty,
        "unit_price": product["price"],
        "gross_revenue": gross,
        "refund_quantity": refund_qty,
        "refund_amount": refund_amt,
        "net_quantity": net_qty,
        "net_revenue": net_rev,
        "product_id": product["product_id"],
        "product_title": product["product_title"],
        "variant_id": f"v{li_id}",
        "sku": product["sku"],
        "variant_title": "Default",
    }


def generate_orders_json() -> None:
    orders = []
    li_counter = 10000
    order_id_counter = 5000

    # Spread ~100 orders across 30 days (June 2025), not every day
    active_days = sorted(random.sample(range(1, 31), 22))  # ~22 active days

    # Which orders get refunds (indices)
    refund_order_indices = set(random.sample(range(100), 10))

    # Which orders get discount codes
    discount_order_indices = set(random.sample(range(100), 3))

    order_idx = 0
    for day in active_days:
        # 3-6 orders per active day
        n_orders = random.randint(3, 6)
        for _ in range(n_orders):
            if order_idx >= 100:
                break

            d = date(2025, 6, day)
            hour = random.randint(8, 22)
            minute = random.randint(0, 59)
            created_at = f"{d.isoformat()}T{hour:02d}:{minute:02d}:00Z"

            # 1-3 line items per order
            n_items = random.choices([1, 2, 3], weights=[0.4, 0.4, 0.2])[0]
            chosen_products = random.sample(PRODUCTS, min(n_items, len(PRODUCTS)))

            line_items = []
            for prod in chosen_products[:n_items]:
                qty = random.randint(1, 5)
                refund_qty = 0
                refund_amt = 0.0
                if order_idx in refund_order_indices and len(line_items) == 0:
                    refund_qty = random.randint(1, min(qty, 2))
                    refund_amt = refund_qty * prod["price"]

                li = make_line_item(li_counter, prod, qty, refund_qty, refund_amt)
                line_items.append(li)
                li_counter += 1

            subtotal = sum(li["gross_revenue"] for li in line_items)
            total_refunded = sum(li["refund_amount"] for li in line_items)
            net_payment = sum(li["net_revenue"] for li in line_items)

            discount_codes = []
            total_discounts = 0.0
            if order_idx in discount_order_indices:
                discount_codes = [{"code": "SAVE10", "amount": "10.00", "type": "percentage"}]
                total_discounts = round(subtotal * 0.10, 2)
                net_payment -= total_discounts

            order = {
                "id": str(order_id_counter),
                "created_at": created_at,
                "local_date": d.isoformat(),
                "financial_status": "PAID",
                "subtotal": subtotal,
                "current_subtotal": net_payment + total_discounts,
                "total_discounts": total_discounts,
                "total_refunded": total_refunded,
                "net_payment": net_payment,
                "currency": "USD",
                "discount_codes": discount_codes,
                "tags": [],
                "source_name": "web",
                "test": False,
                "cancelled_at": None,
                "line_items": line_items,
            }
            orders.append(order)
            order_id_counter += 1
            order_idx += 1

        if order_idx >= 100:
            break

    (FIXTURES / "sample_orders.json").write_text(
        json.dumps(orders, indent=2) + "\n"
    )

    total_li = sum(len(o["line_items"]) for o in orders)
    refund_count = sum(1 for o in orders for li in o["line_items"] if li["refund_quantity"] > 0)
    print(f"Wrote {len(orders)} orders ({total_li} line items, {refund_count} refunds) to sample_orders.json")


if __name__ == "__main__":
    generate_revenue_csv()
    generate_orders_json()
