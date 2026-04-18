"""Core analytics functions -- pure computation layer.

Five functions that consume normalized order dicts and pandas Series,
returning AnalyticsResult objects with markdown-ready output.

All functions are pure (no I/O, no side effects) and can be tested
without MCP runtime.
"""

from __future__ import annotations

import datetime
from collections import defaultdict
from typing import Any

import numpy as np
import pandas as pd

from shopify_forecast_mcp.core.forecast_result import ForecastResult
from shopify_forecast_mcp.core.metrics import (
    SUPPORTED_METRICS,
    AnalyticsResult,
    AnalyticsSection,
    aggregate_metrics,
    compute_discount_rate,
    compute_units_per_order,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SENSITIVITY_BANDS: dict[str, tuple[str, str]] = {
    "low": ("q10", "q90"),
    "medium": ("q20", "q80"),
    "high": ("q30", "q70"),
}

_METRIC_LABELS: dict[str, str] = {
    "revenue": "Revenue",
    "orders": "Orders",
    "units": "Units",
    "aov": "AOV",
    "discount_rate": "Discount Rate",
    "units_per_order": "Units/Order",
}


def _fmt(value: float, metric: str = "revenue") -> str:
    """Format a numeric value for display in tables."""
    if metric in ("revenue", "aov"):
        return f"${value:,.2f}"
    if metric in ("discount_rate",):
        return f"{value:.1f}%"
    if metric in ("units_per_order",):
        return f"{value:.2f}"
    return f"{value:,.0f}"


def _pct_change(old: float, new: float) -> float:
    """Compute percentage change, handling zero division."""
    if old == 0:
        return 0.0 if new == 0 else 100.0
    return ((new - old) / abs(old)) * 100


# ---------------------------------------------------------------------------
# 1. analyze_promotion
# ---------------------------------------------------------------------------


def analyze_promotion(
    orders: list[dict],
    promo_start: datetime.date,
    promo_end: datetime.date,
    baseline_days: int = 30,
    promo_name: str = "",
) -> AnalyticsResult:
    """Analyze promotional impact with lift, post-promo hangover, and cannibalization.

    Args:
        orders: Normalized order dicts with local_date, line_items, discount_codes.
        promo_start: First day of the promotion (inclusive).
        promo_end: Last day of the promotion (inclusive).
        baseline_days: Number of days before promo_start to use as baseline.
        promo_name: Human-readable name for the promotion.

    Returns:
        AnalyticsResult with sections for lift, post-promo impact, and cannibalization.
    """
    # Validate dates (T-05-01)
    if promo_end < promo_start:
        return AnalyticsResult(
            title="Promotion Analysis Error",
            sections=[],
            summary="Error: promo_end must be on or after promo_start.",
            recommendations=[],
            metadata={"error": True},
        )

    promo_duration = (promo_end - promo_start).days + 1
    baseline_start = promo_start - datetime.timedelta(days=baseline_days)
    baseline_end = promo_start - datetime.timedelta(days=1)
    post_promo_start = promo_end + datetime.timedelta(days=1)
    post_promo_end = promo_end + datetime.timedelta(days=promo_duration)

    baseline_str = (baseline_start.isoformat(), baseline_end.isoformat())
    promo_str = (promo_start.isoformat(), promo_end.isoformat())
    post_str = (post_promo_start.isoformat(), post_promo_end.isoformat())

    baseline_metrics = aggregate_metrics(orders, *baseline_str)
    promo_metrics = aggregate_metrics(orders, *promo_str)
    post_metrics = aggregate_metrics(orders, *post_str)

    # Daily averages
    baseline_days_actual = max((baseline_end - baseline_start).days + 1, 1)
    promo_days_actual = promo_duration
    post_days_actual = promo_duration

    sections: list[AnalyticsSection] = []
    recommendations: list[str] = []

    # --- Section 1: Promotion Impact ---
    rows: list[list[str]] = []
    for m in ("revenue", "orders", "units", "aov", "discount_rate", "units_per_order"):
        label = _METRIC_LABELS.get(m, m)
        b_daily = baseline_metrics[m] / baseline_days_actual if m not in ("aov", "discount_rate", "units_per_order") else baseline_metrics[m]
        p_daily = promo_metrics[m] / promo_days_actual if m not in ("aov", "discount_rate", "units_per_order") else promo_metrics[m]
        change = p_daily - b_daily
        lift = _pct_change(b_daily, p_daily)
        rows.append([
            label,
            _fmt(b_daily, m),
            _fmt(p_daily, m),
            _fmt(change, m),
            f"{lift:+.1f}%",
        ])

    sections.append(AnalyticsSection(
        heading="Promotion Impact",
        table_headers=["Metric", "Baseline (daily avg)", "Promo (daily avg)", "Change", "Lift %"],
        table_rows=rows,
    ))

    # --- Section 2: Post-Promo Impact (D-04) ---
    post_rows: list[list[str]] = []
    for m in ("revenue", "orders"):
        label = _METRIC_LABELS.get(m, m)
        b_daily = baseline_metrics[m] / baseline_days_actual
        pp_daily = post_metrics[m] / post_days_actual if post_days_actual > 0 else 0
        change_pct = _pct_change(b_daily, pp_daily)
        post_rows.append([label, _fmt(b_daily, m), _fmt(pp_daily, m), f"{change_pct:+.1f}%"])

    sections.append(AnalyticsSection(
        heading="Post-Promo Impact",
        table_headers=["Metric", "Baseline (daily avg)", "Post-Promo (daily avg)", "Change %"],
        table_rows=post_rows,
    ))

    # --- Section 3: Product Cannibalization (D-05) ---
    # Compute revenue share by product for baseline vs promo
    baseline_orders = [o for o in orders if baseline_str[0] <= o["local_date"] <= baseline_str[1]]
    promo_orders = [o for o in orders if promo_str[0] <= o["local_date"] <= promo_str[1]]

    def _product_shares(order_list: list[dict]) -> dict[str, float]:
        rev_by_product: dict[str, float] = defaultdict(float)
        for o in order_list:
            for li in o.get("line_items", []):
                rev_by_product[li["product_id"]] += li["net_revenue"]
        total = sum(rev_by_product.values())
        if total == 0:
            return {}
        return {pid: (rev / total) * 100 for pid, rev in rev_by_product.items()}

    baseline_shares = _product_shares(baseline_orders)
    promo_shares = _product_shares(promo_orders)
    all_products = set(baseline_shares.keys()) | set(promo_shares.keys())

    cann_rows: list[list[str]] = []
    cannibalized_products: list[str] = []
    for pid in sorted(all_products):
        b_share = baseline_shares.get(pid, 0.0)
        p_share = promo_shares.get(pid, 0.0)
        change_pp = p_share - b_share
        cann_rows.append([pid, f"{b_share:.1f}%", f"{p_share:.1f}%", f"{change_pp:+.1f}pp"])
        if change_pp < -2.0:
            cannibalized_products.append(pid)

    sections.append(AnalyticsSection(
        heading="Product Cannibalization",
        table_headers=["Product", "Baseline Share %", "Promo Share %", "Change pp"],
        table_rows=cann_rows,
    ))

    # --- Summary & Recommendations ---
    rev_lift = _pct_change(
        baseline_metrics["revenue"] / baseline_days_actual,
        promo_metrics["revenue"] / promo_days_actual,
    )
    post_rev_change = _pct_change(
        baseline_metrics["revenue"] / baseline_days_actual,
        post_metrics["revenue"] / post_days_actual if post_days_actual > 0 else 0,
    )

    name_label = promo_name or "the promotion"
    summary = (
        f"Revenue lifted {rev_lift:+.1f}% during {name_label} "
        f"({promo_start} to {promo_end}). "
        f"Post-promo revenue dipped {post_rev_change:+.1f}% vs baseline."
    )

    if abs(post_rev_change) > 10:
        recommendations.append(
            "Consider a shorter promo to reduce post-promo dip."
        )
    if cannibalized_products:
        products_str = ", ".join(cannibalized_products)
        recommendations.append(
            f"Products {products_str} lost share during promo -- "
            "consider excluding from discount."
        )
    if not recommendations:
        recommendations.append("Promotion performance was balanced across products.")

    return AnalyticsResult(
        title="Promotion Analysis",
        sections=sections,
        summary=summary,
        recommendations=recommendations,
        metadata={
            "promo_start": promo_start.isoformat(),
            "promo_end": promo_end.isoformat(),
            "promo_name": promo_name,
        },
    )


# ---------------------------------------------------------------------------
# 2. detect_anomalies
# ---------------------------------------------------------------------------


def detect_anomalies(
    series: pd.Series,
    forecast_result: ForecastResult,
    sensitivity: str = "medium",
    lookback_days: int = 90,
    known_events: list[dict[str, str]] | None = None,
) -> AnalyticsResult:
    """Detect anomalies by comparing actuals against forecast quantile bands.

    Args:
        series: Daily actuals with DatetimeIndex.
        forecast_result: ForecastResult with confidence_bands (quantile channels).
        sensitivity: "low", "medium", or "high" -- maps to quantile band width.
        lookback_days: Number of recent days to analyze.
        known_events: Optional list of {"date": "YYYY-MM-DD", "label": "..."} for labeling.

    Returns:
        AnalyticsResult with anomaly clusters, directions, and recommendations.
    """
    if known_events is None:
        known_events = []

    # Validate sensitivity
    if sensitivity not in SENSITIVITY_BANDS:
        sensitivity = "medium"

    lower_band_key, upper_band_key = SENSITIVITY_BANDS[sensitivity]

    # Auto-clamp lookback to available data (D-13)
    actual_lookback = min(lookback_days, len(series))
    short_history = len(series) < 90

    # Align series and forecast bands
    series_tail = series.iloc[-actual_lookback:]

    lower_band = forecast_result.confidence_bands.get(lower_band_key)
    upper_band = forecast_result.confidence_bands.get(upper_band_key)
    mean_band = forecast_result.confidence_bands.get("mean")

    if lower_band is None or upper_band is None or mean_band is None:
        return AnalyticsResult(
            title="Anomaly Detection",
            sections=[],
            summary="Error: Forecast result missing required quantile bands.",
            recommendations=[],
            metadata={"error": True},
        )

    # Clamp band arrays to match series length
    band_len = min(len(lower_band), actual_lookback)
    lower_vals = lower_band[-band_len:]
    upper_vals = upper_band[-band_len:]
    mean_vals = mean_band[-band_len:]
    series_vals = series_tail.iloc[-band_len:]

    # Find anomaly days
    anomaly_days: list[dict[str, Any]] = []
    for i in range(len(series_vals)):
        actual = float(series_vals.iloc[i])
        expected = float(mean_vals[i])
        lower = float(lower_vals[i])
        upper = float(upper_vals[i])

        if actual > upper or actual < lower:
            date = series_vals.index[i]
            deviation = _pct_change(expected, actual) if expected != 0 else 0.0
            direction = "Spike" if actual > upper else "Drop"
            anomaly_days.append({
                "date": date,
                "actual": actual,
                "expected": expected,
                "lower": lower,
                "upper": upper,
                "deviation": deviation,
                "direction": direction,
            })

    # Cluster consecutive anomaly days (D-08): gap <= 1 day merges
    clusters: list[list[dict]] = []
    for day in anomaly_days:
        if clusters and (day["date"] - clusters[-1][-1]["date"]).days <= 2:
            clusters[-1].append(day)
        else:
            clusters.append([day])

    # Build event lookup for labeling (D-09)
    event_lookup: dict[str, str] = {}
    for ev in known_events:
        event_lookup[ev["date"]] = ev["label"]

    # Build table rows (D-11)
    rows: list[list[str]] = []
    for cluster in clusters:
        start_date = cluster[0]["date"]
        end_date = cluster[-1]["date"]

        if start_date == end_date:
            date_range = start_date.strftime("%Y-%m-%d")
        else:
            date_range = f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"

        total_actual = sum(d["actual"] for d in cluster)
        total_expected = sum(d["expected"] for d in cluster)
        avg_deviation = np.mean([d["deviation"] for d in cluster])
        direction = cluster[0]["direction"]
        band_label = f"{lower_band_key}/{upper_band_key}"

        # Direction format (D-10)
        if direction == "Spike":
            dir_str = f"Spike (+{abs(avg_deviation):.0f}% above expected)"
        else:
            dir_str = f"Drop (-{abs(avg_deviation):.0f}% below expected)"

        # Check for event labels (D-09)
        for d in cluster:
            date_str = d["date"].strftime("%Y-%m-%d")
            if date_str in event_lookup:
                dir_str += f" (likely: {event_lookup[date_str]})"
                break

        rows.append([
            date_range,
            dir_str,
            f"{total_actual:,.0f}",
            f"{total_expected:,.0f}",
            band_label,
            f"{avg_deviation:+.1f}%",
        ])

    sections = [AnalyticsSection(
        heading="Anomaly Clusters",
        table_headers=["Date Range", "Direction", "Actual", "Expected", "Band", "Deviation %"],
        table_rows=rows,
    )]

    # Summary
    warning = ""
    if short_history:
        warning = f"Limited history ({len(series)} days) -- anomaly detection may be less reliable. "

    if clusters:
        summary = (
            f"{warning}{len(clusters)} anomaly cluster(s) detected in the last "
            f"{actual_lookback} days."
        )
    else:
        summary = f"{warning}No anomalies detected in the last {actual_lookback} days."

    # Recommendations
    recommendations: list[str] = []
    if clusters:
        for cluster in clusters:
            start = cluster[0]["date"].strftime("%Y-%m-%d")
            end = cluster[-1]["date"].strftime("%Y-%m-%d")
            direction = cluster[0]["direction"]
            label = ""
            for d in cluster:
                date_str = d["date"].strftime("%Y-%m-%d")
                if date_str in event_lookup:
                    label = f" (aligns with {event_lookup[date_str]})"
                    break
            recommendations.append(
                f"The {start} to {end} {direction.lower()}{label} warrants investigation."
            )
    else:
        recommendations.append("No anomalies found -- the series is within expected bounds.")

    return AnalyticsResult(
        title="Anomaly Detection",
        sections=sections,
        summary=summary,
        recommendations=recommendations,
        metadata={
            "sensitivity": sensitivity,
            "lookback_days": actual_lookback,
            "clusters_found": len(clusters),
        },
    )


# ---------------------------------------------------------------------------
# 3. compare_periods
# ---------------------------------------------------------------------------


def compare_periods(
    orders: list[dict],
    period_a_start: datetime.date,
    period_a_end: datetime.date,
    period_b_start: datetime.date,
    period_b_end: datetime.date,
    metrics: tuple[str, ...] | list[str] | None = None,
) -> AnalyticsResult:
    """Compare two time periods across all supported metrics.

    Args:
        orders: Normalized order dicts.
        period_a_start/end: First period date range.
        period_b_start/end: Second period date range.
        metrics: Metrics to compare. Defaults to all SUPPORTED_METRICS.

    Returns:
        AnalyticsResult with comparison table and biggest movers highlighted.
    """
    if metrics is None:
        metrics = SUPPORTED_METRICS

    # Validate dates (T-05-01)
    if period_a_end < period_a_start or period_b_end < period_b_start:
        return AnalyticsResult(
            title="Period Comparison Error",
            sections=[],
            summary="Error: end date must be on or after start date for both periods.",
            recommendations=[],
            metadata={"error": True},
        )

    a_metrics = aggregate_metrics(orders, period_a_start.isoformat(), period_a_end.isoformat())
    b_metrics = aggregate_metrics(orders, period_b_start.isoformat(), period_b_end.isoformat())

    # Compute changes and find biggest mover
    changes: dict[str, float] = {}
    for m in metrics:
        changes[m] = abs(_pct_change(a_metrics.get(m, 0), b_metrics.get(m, 0)))

    biggest_mover = max(changes, key=lambda k: changes[k]) if changes else None

    # Build table rows (D-03)
    rows: list[list[str]] = []
    for m in metrics:
        label = _METRIC_LABELS.get(m, m)
        a_val = a_metrics.get(m, 0.0)
        b_val = b_metrics.get(m, 0.0)
        change = b_val - a_val
        change_pct = _pct_change(a_val, b_val)

        # Bold the biggest mover
        if m == biggest_mover:
            label = f"**{label}**"

        rows.append([
            label,
            _fmt(a_val, m),
            _fmt(b_val, m),
            _fmt(change, m),
            f"{change_pct:+.1f}%",
        ])

    sections = [AnalyticsSection(
        heading="Period Comparison",
        table_headers=["Metric", "Period A", "Period B", "Change", "Change %"],
        table_rows=rows,
    )]

    # Summary
    rev_change = _pct_change(a_metrics.get("revenue", 0), b_metrics.get("revenue", 0))
    ord_change = _pct_change(a_metrics.get("orders", 0), b_metrics.get("orders", 0))
    rev_dir = "up" if rev_change >= 0 else "down"
    ord_dir = "up" if ord_change >= 0 else "down"
    summary = (
        f"Period B vs Period A: Revenue {rev_dir} {abs(rev_change):.1f}%, "
        f"Orders {ord_dir} {abs(ord_change):.1f}%."
    )

    # Recommendations
    recommendations: list[str] = []
    if biggest_mover:
        bm_label = _METRIC_LABELS.get(biggest_mover, biggest_mover)
        bm_change = _pct_change(a_metrics.get(biggest_mover, 0), b_metrics.get(biggest_mover, 0))
        bm_dir = "increased" if bm_change >= 0 else "decreased"
        recommendations.append(
            f"{bm_label} {bm_dir} {abs(bm_change):.1f}% -- worth investigating the driver."
        )

    return AnalyticsResult(
        title="Period Comparison",
        sections=sections,
        summary=summary,
        recommendations=recommendations,
        metadata={
            "period_a": f"{period_a_start} to {period_a_end}",
            "period_b": f"{period_b_start} to {period_b_end}",
        },
    )


# ---------------------------------------------------------------------------
# 4. get_seasonality
# ---------------------------------------------------------------------------

_DOW_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def get_seasonality(
    series: pd.Series,
    granularity: str = "day_of_week",
) -> AnalyticsResult:
    """Compute seasonality index table (100 = average baseline).

    Args:
        series: Daily pd.Series with DatetimeIndex.
        granularity: "day_of_week", "monthly", or "quarterly".

    Returns:
        AnalyticsResult with index table and peak/trough identification.
    """
    warnings: list[str] = []

    if granularity == "day_of_week":
        groups = series.groupby(series.index.dayofweek).mean()
        overall_mean = groups.mean()
        index_vals = (groups / overall_mean * 100) if overall_mean != 0 else groups * 0

        rows: list[list[str]] = []
        for dow in range(7):
            name = _DOW_NAMES[dow]
            idx = float(index_vals.get(dow, 100.0))
            interp = "Above average" if idx > 110 else ("Below average" if idx < 90 else "Average")
            rows.append([name, f"{idx:.0f}", interp])

    elif granularity == "monthly":
        # Check data coverage
        months_covered = series.index.to_period("M").nunique()
        if months_covered < 12:
            warnings.append(f"Only {months_covered} months of data available.")

        groups = series.groupby(series.index.month).mean()
        overall_mean = groups.mean()
        index_vals = (groups / overall_mean * 100) if overall_mean != 0 else groups * 0

        rows = []
        for month in range(1, 13):
            name = _MONTH_NAMES[month - 1]
            idx = float(index_vals.get(month, 100.0))
            interp = "Above average" if idx > 110 else ("Below average" if idx < 90 else "Average")
            rows.append([name, f"{idx:.0f}", interp])

    elif granularity == "quarterly":
        years_covered = series.index.to_period("Y").nunique()
        if years_covered < 2:
            warnings.append(f"Only {years_covered} year(s) of data available.")

        groups = series.groupby(series.index.quarter).mean()
        overall_mean = groups.mean()
        index_vals = (groups / overall_mean * 100) if overall_mean != 0 else groups * 0

        rows = []
        for q in range(1, 5):
            name = f"Q{q}"
            idx = float(index_vals.get(q, 100.0))
            interp = "Above average" if idx > 110 else ("Below average" if idx < 90 else "Average")
            rows.append([name, f"{idx:.0f}", interp])
    else:
        return AnalyticsResult(
            title="Seasonality Analysis Error",
            sections=[],
            summary=f"Error: Unknown granularity '{granularity}'. Use day_of_week, monthly, or quarterly.",
            recommendations=[],
            metadata={"error": True},
        )

    sections = [AnalyticsSection(
        heading="Seasonality Index",
        table_headers=["Period", "Index", "Interpretation"],
        table_rows=rows,
    )]

    # Identify peak and trough
    index_values = {row[0]: float(row[1]) for row in rows}
    peak = max(index_values, key=index_values.get)  # type: ignore[arg-type]
    trough = min(index_values, key=index_values.get)  # type: ignore[arg-type]

    warning_prefix = " ".join(warnings) + " " if warnings else ""
    summary = (
        f"{warning_prefix}{peak} is the strongest period (index {index_values[peak]:.0f}), "
        f"{trough} is weakest (index {index_values[trough]:.0f})."
    )

    recommendations = [
        f"Consider running promotions on slower periods ({trough}) to balance demand."
    ]

    return AnalyticsResult(
        title="Seasonality Analysis",
        sections=sections,
        summary=summary,
        recommendations=recommendations,
        metadata={"granularity": granularity},
    )


# ---------------------------------------------------------------------------
# 5. cohort_retention
# ---------------------------------------------------------------------------


def cohort_retention(
    orders: list[dict],
    cohort_period: str = "monthly",
    periods_out: int = 6,
) -> AnalyticsResult:
    """Compute cohort retention matrix with LTV.

    Args:
        orders: Normalized order dicts with customer_id and local_date.
        cohort_period: "monthly" or "weekly" -- defines cohort grouping.
        periods_out: Number of subsequent periods to track.

    Returns:
        AnalyticsResult with retention matrix and LTV per cohort.
    """
    if not orders:
        return AnalyticsResult(
            title="Cohort Retention",
            sections=[],
            summary="No orders available for cohort analysis.",
            recommendations=[],
        )

    # Build customer -> first purchase date and all purchase dates
    customer_first: dict[str, datetime.date] = {}
    customer_purchases: dict[str, list[tuple[datetime.date, float]]] = defaultdict(list)

    for o in orders:
        cust_id = o.get("customer_id", "unknown")
        if cust_id == "unknown":
            continue
        local_date = datetime.date.fromisoformat(o["local_date"])
        revenue = sum(li["net_revenue"] for li in o.get("line_items", []))

        if cust_id not in customer_first or local_date < customer_first[cust_id]:
            customer_first[cust_id] = local_date
        customer_purchases[cust_id].append((local_date, revenue))

    if not customer_first:
        return AnalyticsResult(
            title="Cohort Retention",
            sections=[],
            summary="No customer data available for cohort analysis.",
            recommendations=[],
        )

    # Assign customers to cohorts
    def _cohort_key(dt: datetime.date) -> str:
        if cohort_period == "weekly":
            # ISO week
            yr, wk, _ = dt.isocalendar()
            return f"{yr}-W{wk:02d}"
        else:
            return dt.strftime("%Y-%m")

    def _period_diff(first_date: datetime.date, purchase_date: datetime.date) -> int:
        """Return the period number (0-based) of a purchase relative to first purchase."""
        if cohort_period == "weekly":
            return (purchase_date - first_date).days // 7
        else:
            return (purchase_date.year - first_date.year) * 12 + (purchase_date.month - first_date.month)

    # Build cohort data
    cohorts: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "customers": set(),
        "period_customers": defaultdict(set),
        "total_revenue": 0.0,
    })

    for cust_id, first_date in customer_first.items():
        cohort_key = _cohort_key(first_date)
        cohorts[cohort_key]["customers"].add(cust_id)

        for purchase_date, revenue in customer_purchases[cust_id]:
            period = _period_diff(first_date, purchase_date)
            if 0 <= period <= periods_out:
                cohorts[cohort_key]["period_customers"][period].add(cust_id)
            cohorts[cohort_key]["total_revenue"] += revenue

    # Build table
    headers = ["Cohort", "Size"] + [f"P{i}%" for i in range(1, periods_out + 1)] + ["Avg LTV"]
    rows: list[list[str]] = []
    period_retention_sums: dict[int, list[float]] = defaultdict(list)

    for cohort_key in sorted(cohorts.keys()):
        data = cohorts[cohort_key]
        size = len(data["customers"])
        if size == 0:
            continue

        row = [cohort_key, str(size)]
        for p in range(1, periods_out + 1):
            retained = len(data["period_customers"].get(p, set()))
            rate = (retained / size) * 100
            row.append(f"{rate:.0f}%")
            period_retention_sums[p].append(rate)

        avg_ltv = data["total_revenue"] / size
        row.append(f"${avg_ltv:,.2f}")
        rows.append(row)

    # Add summary row (average retention per period)
    avg_row = ["**Average**", ""]
    best_retention_p1 = 0.0
    best_cohort = ""
    for p in range(1, periods_out + 1):
        vals = period_retention_sums.get(p, [0.0])
        avg = np.mean(vals) if vals else 0.0
        avg_row.append(f"{avg:.0f}%")
    avg_row.append("")
    rows.append(avg_row)

    # Find best cohort for P1 retention
    for cohort_key in sorted(cohorts.keys()):
        data = cohorts[cohort_key]
        size = len(data["customers"])
        if size == 0:
            continue
        p1_retained = len(data["period_customers"].get(1, set()))
        p1_rate = (p1_retained / size) * 100
        if p1_rate > best_retention_p1:
            best_retention_p1 = p1_rate
            best_cohort = cohort_key

    sections = [AnalyticsSection(
        heading="Retention Matrix",
        table_headers=headers,
        table_rows=rows,
    )]

    avg_p1 = np.mean(period_retention_sums.get(1, [0.0]))
    summary = (
        f"Average {cohort_period} retention (P1) is {avg_p1:.0f}%. "
        f"Best cohort: {best_cohort} at {best_retention_p1:.0f}%."
    )

    recommendations: list[str] = []
    # Check for sharp drop-off
    if len(period_retention_sums) >= 2:
        p1_avg = np.mean(period_retention_sums.get(1, [0]))
        p2_avg = np.mean(period_retention_sums.get(2, [0]))
        if p1_avg > 0 and (p1_avg - p2_avg) / p1_avg > 0.3:
            recommendations.append(
                "Retention drops sharply after period 1 -- "
                "consider a re-engagement campaign at the 60-day mark."
            )
    if not recommendations:
        recommendations.append(
            "Monitor retention trends across cohorts to identify engagement opportunities."
        )

    # Add LTV info
    total_customers = sum(len(cohorts[k]["customers"]) for k in cohorts)
    total_revenue = sum(cohorts[k]["total_revenue"] for k in cohorts)
    avg_ltv_overall = total_revenue / total_customers if total_customers > 0 else 0
    summary += f" Overall avg LTV: ${avg_ltv_overall:,.2f}."

    return AnalyticsResult(
        title="Cohort Retention Analysis",
        sections=sections,
        summary=summary,
        recommendations=recommendations,
        metadata={
            "cohort_period": cohort_period,
            "periods_out": periods_out,
            "total_cohorts": len([k for k in cohorts if len(cohorts[k]["customers"]) > 0]),
        },
    )
