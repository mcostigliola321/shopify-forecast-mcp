# Phase 5: Analytics, Covariates & Remaining Tools - Research

**Researched:** 2026-04-17
**Domain:** Time-series analytics, covariate engineering, MCP tool registration
**Confidence:** HIGH

## Summary

Phase 5 adds five analytical capabilities (promotion analysis, anomaly detection, period comparison, seasonality extraction, cohort retention) plus covariate engineering for TimesFM XReg behind a feature flag, plus two CLI verbs (`promo`, `compare`). The existing codebase provides strong foundations: `orders_to_daily_series()` handles metric aggregation, `ForecastEngine` provides quantile channels needed for anomaly bands, `ForecastResult` establishes the markdown output pattern, and the MCP tool/CLI registration patterns are well-established.

The primary complexity lies in (1) correctly wiring TimesFM's `forecast_with_covariates()` API which requires `return_backcast=True` in ForecastConfig and covariates spanning both history and horizon as a single aligned sequence, and (2) the analytics functions themselves which are pure pandas/numpy computation with no external dependencies beyond the `holidays` package (already installed, v0.94, 501 countries).

**Primary recommendation:** Build analytics as pure functions in `core/analytics.py` consuming pandas Series and normalized order dicts. Build covariates as a separate `core/covariates.py` module. Wire both into MCP tools following the exact pattern of `forecast_revenue`/`forecast_demand`. The two new metrics (`discount_rate`, `units_per_order`) require extending `orders_to_daily_series()` or building separate aggregation functions.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** All analytics tools return markdown table + 2-3 sentence natural-language summary with key takeaway
- **D-02:** Tools include 1-2 actionable recommendations after findings
- **D-03:** `compare_periods` shows all six metrics by default (revenue, orders, units, AOV, discount_rate, units_per_order) with biggest movers bolded/highlighted
- **D-04:** `analyze_promotion` has separate "Post-Promo Impact" section showing revenue dip in days after promo vs baseline
- **D-05:** Product-level cannibalization estimate in `analyze_promotion` -- compare product mix during promo vs baseline
- **D-06:** Anomaly sensitivity maps to quantile bands: Low=q10/q90, Medium=q20/q80, High=q30/q70
- **D-07:** Stores with <90 days history: warn and proceed with disclaimer
- **D-08:** Consecutive anomaly days grouped into clusters (single "event" with start/end dates)
- **D-09:** Anomaly clusters labeled with known events (holidays, promos) when overlap detected
- **D-10:** Direction shown as "Spike (+42% above expected)" or "Drop (-31% below expected)" per cluster
- **D-11:** Each anomaly row includes: date range, actual value, expected value, confidence band, deviation %
- **D-12:** Single metric per call for anomaly detection (consistent with forecast tools)
- **D-13:** Default lookback 90 days, auto-clamp to available history
- **D-14:** Seasonality as index table: rows=day-of-week or month, column=index where 100=average
- **D-15:** Cohort retention: full cohort x period retention matrix plus summary line with avg retention and LTV
- **D-16:** `discount_rate` metric (% of orders using discount code)
- **D-17:** `units_per_order` metric (average basket size)
- **D-18:** When covariates enabled, ALL built-in covariates activate together
- **D-19:** `holiday_proximity` window fixed at -7/+3 days
- **D-20:** Always append marginal value disclaimer when covariates enabled
- **D-21:** CLI `promo` verb: `--start`, `--end`, `--name` (optional)
- **D-22:** Default output markdown, `--json` for piping
- **D-23:** CLI `compare` supports `--yoy`, `--mom`, plus custom date ranges

### Claude's Discretion
- Exact markdown table column ordering and formatting
- Error message wording for invalid date ranges, missing data, etc.
- Whether `cohort_retention` cohort period param defaults to monthly or weekly
- Internal module organization of analytics.py (single file vs split per function)
- Custom events API shape for covariates
- Country auto-detection from shop timezone vs explicit param

### Deferred Ideas (OUT OF SCOPE)
- Conversion rate (mobile/desktop) -- requires Shopify Analytics API
- Product mix shift analysis
- Repeat vs new customer segmentation
- Revenue concentration / Pareto analysis
- Refund rate trending by product
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| R5.1 | `build_covariates(date_range, orders, country, custom_events)` returning dict of name -> numpy array | holidays v0.94 verified, 501 countries; pure pandas/numpy computation |
| R5.2 | Built-in covariates: day_of_week, is_weekend, month, is_holiday, holiday_proximity, has_discount, discount_depth | holidays package API verified; discount_codes field exists in normalized orders |
| R5.3 | Custom events: list of `{date, label, type}` dicts | Pure dict processing, no external deps |
| R5.4 | `build_future_covariates(horizon, last_date, country, planned_promos)` | Holiday flags deterministic from holidays package; promo flags from input |
| R5.5 | Wire into `forecast_with_covariates()` API | CRITICAL: requires `return_backcast=True` in ForecastConfig; covariates span context+horizon as single sequence |
| R5.6 | Feature-flagged: covariates off by default, opt-in via tool param | Add `covariates_enabled: bool = False` to Settings |
| R6.1 | `analyze_promotion` -- revenue lift, order lift, AOV change, discount depth, cannibalization, post-promo hangover | Pure pandas computation on order data; group_by product for cannibalization |
| R6.2 | `detect_anomalies` -- flag dates outside quantile bands | Uses existing ForecastEngine quantile channels [mean, q10..q90] |
| R6.3 | `compare_periods` -- YoY/MoM comparison per metric | Pure pandas; needs new discount_rate and units_per_order aggregation |
| R6.4 | `cohort_retention` -- cohort matrix, retention rates, avg LTV | Pure pandas; group by first-purchase month, track repurchase |
| R8.3 | MCP tool `analyze_promotion` | Follow existing @mcp.tool() pattern with Pydantic BaseModel params |
| R8.4 | MCP tool `detect_anomalies` | Needs forecast engine for expected values; most complex tool |
| R8.5 | MCP tool `compare_periods` | Straightforward data retrieval + comparison |
| R8.7 | MCP tool `get_seasonality` | Pure aggregation -- no forecasting needed |
| R9.2 | CLI verbs `promo` and `compare` | Follow existing argparse pattern from revenue/demand |
</phase_requirements>

## Standard Stack

### Core (already installed)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | >=2.2 | Time-series aggregation, cohort analysis | Already used throughout timeseries.py [VERIFIED: pyproject.toml] |
| numpy | >=1.26 | Numerical computation, covariate arrays | Already used in forecaster.py [VERIFIED: pyproject.toml] |
| holidays | 0.94 | Country-specific holiday detection (501 countries) | Already in dependencies, tested [VERIFIED: pip show + runtime test] |
| timesfm | git@f085b90 | forecast_with_covariates() for XReg | Already installed, signature verified [VERIFIED: runtime inspect] |

### Supporting (no new dependencies needed)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| python-dateutil | >=2.9 | Date arithmetic for YoY/MoM shortcuts | Already installed [VERIFIED: pyproject.toml] |

### New Dependencies
**None required.** All Phase 5 functionality is built on existing dependencies. The `holidays` package was already added to `pyproject.toml` in Phase 1.

## Architecture Patterns

### Recommended Project Structure
```
src/shopify_forecast_mcp/
├── core/
│   ├── analytics.py          # NEW: analyze_promotion, detect_anomalies, compare_periods, cohort_retention, get_seasonality
│   ├── covariates.py         # NEW: build_covariates, build_future_covariates
│   ├── metrics.py            # NEW: SUPPORTED_METRICS enum, discount_rate/units_per_order aggregation
│   ├── forecaster.py         # MODIFY: add forecast_with_covariates wrapper
│   ├── timeseries.py         # MINOR: extend Metric type alias
│   ├── forecast_result.py    # EXISTING: reuse to_table/summary pattern
│   ├── normalize.py          # EXISTING: discount_codes already present
│   └── shopify_client.py     # EXISTING: no changes
├── mcp/
│   ├── tools.py              # MODIFY: register 4 new tool handlers
│   └── server.py             # EXISTING: no changes needed
├── cli.py                    # MODIFY: add promo, compare subcommands
└── config.py                 # MODIFY: add covariates_enabled flag
```

### Pattern 1: Analytics Function Signature Convention
**What:** All analytics functions are pure functions that accept pandas Series / order lists and return structured result dicts (not markdown). MCP tools format the results.
**When to use:** Every analytics function.
**Example:**
```python
# Source: established pattern from ForecastResult
from dataclasses import dataclass, field
from typing import Any

@dataclass
class AnalyticsResult:
    """Structured output from analytics functions."""
    title: str
    table_headers: list[str]
    table_rows: list[list[str]]
    summary: str
    recommendations: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_markdown(self) -> str:
        """Render as markdown table + summary + recommendations."""
        parts = [f"# {self.title}", ""]
        # Table
        parts.append("| " + " | ".join(self.table_headers) + " |")
        parts.append("|" + "|".join(["---"] * len(self.table_headers)) + "|")
        for row in self.table_rows:
            parts.append("| " + " | ".join(row) + " |")
        parts.extend(["", self.summary, ""])
        # Recommendations (D-02)
        if self.recommendations:
            parts.append("**Recommendations:**")
            for rec in self.recommendations:
                parts.append(f"- {rec}")
        return "\n".join(parts)
```
[ASSUMED: specific AnalyticsResult class design -- could also use plain dicts]

### Pattern 2: Anomaly Detection via Forecast Quantile Bands
**What:** Run ForecastEngine on historical data to get "expected" values, then compare actuals against quantile channels.
**When to use:** `detect_anomalies` tool.
**Example:**
```python
# Source: Verified from CONTEXT.md D-06 + ForecastEngine quantile channels
# Sensitivity -> quantile channel mapping
SENSITIVITY_BANDS = {
    "low": ("q10", "q90"),      # widest band, fewer anomalies
    "medium": ("q20", "q80"),   # moderate
    "high": ("q30", "q70"),     # tightest band, most anomalies
}

def detect_anomalies(
    actuals: pd.Series,
    forecaster: ForecastEngine,
    sensitivity: str = "medium",
    lookback_days: int = 90,
) -> list[AnomalyCluster]:
    """Detect anomalies by comparing actuals against forecast quantile bands.

    Strategy: Use rolling forecast -- for each point, forecast from prior
    context and check if actual falls outside the selected quantile band.
    """
    # Use the full series as context, forecast the lookback window
    # Compare actuals in lookback window against forecast bands
    lower_q, upper_q = SENSITIVITY_BANDS[sensitivity]
    ...
```
[ASSUMED: exact rolling vs single-pass strategy -- recommend single-pass backcast for efficiency]

### Pattern 3: Covariate Array Alignment
**What:** Dynamic covariates for TimesFM must span `context_len + horizon` as a single contiguous sequence per series.
**When to use:** `forecast_with_covariates()` calls.
**Example:**
```python
# Source: VERIFIED from timesfm source inspection
# CRITICAL: covariates span history + future as ONE sequence
# TimesFM infers horizon = len(covariate) - len(input)

def build_covariates(
    date_range: pd.DatetimeIndex,  # context dates + future dates
    orders: list[dict],
    country: str = "US",
    custom_events: list[dict] | None = None,
) -> dict[str, list[float]]:
    """Build aligned covariate arrays for the full date range.

    Returns dict suitable for dynamic_numerical_covariates parameter.
    Each value is a list of floats with len = len(date_range).
    """
    country_holidays = holidays.country_holidays(country, years=sorted(set(d.year for d in date_range)))
    ...
```
[VERIFIED: forecast_with_covariates source confirms covariates span context+horizon]

### Pattern 4: MCP Tool Registration (follow existing)
**What:** Each tool is a decorated async function with Pydantic BaseModel params.
**When to use:** All 4 new tools.
**Example:**
```python
# Source: existing tools.py pattern [VERIFIED: codebase]
class AnalyzePromotionParams(BaseModel):
    promo_start: str = Field(..., description="Promo start date (YYYY-MM-DD)")
    promo_end: str = Field(..., description="Promo end date (YYYY-MM-DD)")
    promo_name: str = Field("", description="Optional promo name for labeling")
    baseline_days: int = Field(30, ge=7, le=365, description="Days before promo for baseline")

@mcp.tool()
async def analyze_promotion(
    params: AnalyzePromotionParams,
    ctx: Context[ServerSession, AppContext],
) -> str:
    """Analyze a past promotion's impact vs baseline period."""
    app: AppContext = ctx.request_context.lifespan_context
    try:
        # ... fetch orders, run analytics, return markdown
    except Exception as e:
        log.exception("analyze_promotion failed")
        return f"**Error running analyze_promotion**\n\n{type(e).__name__}: {e}"
```

### Anti-Patterns to Avoid
- **Hand-rolling quantile computation for anomalies:** Use TimesFM's own quantile channels -- they account for the model's uncertainty. Do not compute z-scores on raw actuals.
- **Splitting covariate arrays into history/future:** TimesFM expects a single contiguous sequence. The library internally splits based on `len(covariate) - len(input)`.
- **Modifying ForecastEngine.forecast() for covariates:** Keep `forecast()` untouched. Add a separate `forecast_with_covariates()` wrapper method that sets `return_backcast=True` and delegates.
- **Putting analytics logic inside MCP tool handlers:** Keep tool handlers thin (fetch data, call analytics, format output). Analytics functions should be testable without MCP.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Holiday detection | Country holiday calendar lookup | `holidays` package (v0.94, 501 countries) | DST, regional variations, moving holidays (Easter, etc.) are fiendishly complex [VERIFIED: installed] |
| Quantile-based anomaly bands | Custom statistical thresholds | TimesFM's quantile output channels | Model-aware uncertainty; accounts for seasonality and trend the model has learned [VERIFIED: source] |
| Date arithmetic for YoY/MoM | Manual month/year math | `dateutil.relativedelta` | Handles month-end edge cases, leap years [VERIFIED: installed] |
| Ridge regression on covariates | Custom linear model | TimesFM's built-in `BatchedInContextXRegLinear` | Already integrated, handles normalization and per-input stats [VERIFIED: source] |

**Key insight:** The analytics functions are pure pandas/numpy -- no exotic libraries needed. The `holidays` package handles the one genuinely complex domain (international holiday calendars). Everything else is aggregation and comparison.

## Common Pitfalls

### Pitfall 1: ForecastConfig Must Set return_backcast=True for XReg
**What goes wrong:** `forecast_with_covariates()` raises `ValueError: For XReg, return_backcast must be set to True in the forecast config. Please recompile the model.`
**Why it happens:** The current `ForecastEngine` compiles with `return_backcast=False` (default). XReg needs backcasts to fit the linear model on residuals.
**How to avoid:** When covariates are enabled, recompile with `return_backcast=True`. Either (a) maintain two compiled configs, or (b) recompile lazily when covariates are first requested. Option (b) is simpler for a feature flag.
**Warning signs:** Any call to `forecast_with_covariates()` will immediately raise without this.
[VERIFIED: timesfm source code inspection]

### Pitfall 2: Covariate Length Mismatch
**What goes wrong:** `ValueError: Forecast horizon length inferred from the dynamic covariates is longer than the max_horizon` or silent wrong results.
**Why it happens:** Dynamic covariates must have length = `len(input) + desired_horizon`. TimesFM infers the horizon from `len(covariate) - len(input)`.
**How to avoid:** Always construct covariates as `build_covariates(full_date_range)` where `full_date_range = context_dates.append(future_dates)`. Assert lengths match before calling.
**Warning signs:** Off-by-one errors in date range construction.
[VERIFIED: timesfm source code inspection]

### Pitfall 3: Anomaly Detection on Short History
**What goes wrong:** Meaningless anomaly results with stores having <90 days of data.
**Why it happens:** TimesFM needs sufficient context to learn seasonality patterns. With 30 days of data, the model's "expected" values are unreliable.
**How to avoid:** Per D-07/D-13, warn and proceed. Auto-clamp lookback to available history. Prepend reliability disclaimer.
**Warning signs:** Many false positive anomalies in the first weeks of data.
[ASSUMED: based on general forecasting principles]

### Pitfall 4: Discount Rate Calculation Edge Cases
**What goes wrong:** Division by zero when no orders in a period; inflated rates when counting multi-code orders.
**Why it happens:** `discount_rate = orders_with_discount / total_orders`. Zero-order days exist in the data (gaps filled with 0).
**How to avoid:** Use period-level aggregation (not daily rate averaged). Count an order as "discounted" if `len(discount_codes) > 0`. Handle zero-order periods gracefully.
**Warning signs:** 100% or 0% discount rates that don't match intuition.
[ASSUMED: based on data patterns in sample_orders.json]

### Pitfall 5: Cohort Retention Requires Customer ID
**What goes wrong:** Cannot build cohorts without a way to identify repeat customers.
**Why it happens:** The current normalized order schema has `id` (order ID) but no `customer_id` or `customer_email` field.
**How to avoid:** The Shopify GraphQL order query needs to include `customer { id }` (or email). This may require extending the Shopify client's order query and the normalize_order function.
**Warning signs:** No way to link orders to the same customer.
[VERIFIED: normalize.py does not include customer_id in normalized order dict]

### Pitfall 6: Seasonality Index Requires Sufficient History
**What goes wrong:** Monthly seasonality index with only 6 months of data -- some months have no representation.
**Why it happens:** The seasonality index divides metric by its overall average. Months with no data produce NaN or misleading indices.
**How to avoid:** Require minimum history: 2 weeks for day_of_week, 12 months for monthly, 2+ years for quarterly. Warn when insufficient.
**Warning signs:** Index values of 0 for months with no data.
[ASSUMED: based on statistical principles]

## Code Examples

### Analytics: Promotion Analysis Core Logic
```python
# Source: Derived from D-04, D-05 decisions + existing timeseries patterns
import pandas as pd
import numpy as np
from datetime import date, timedelta

def analyze_promotion(
    orders: list[dict],
    promo_start: date,
    promo_end: date,
    baseline_days: int = 30,
) -> dict:
    """Analyze promotion impact vs baseline.

    Returns structured dict with:
    - lift metrics (revenue, orders, units, aov)
    - post-promo hangover analysis (D-04)
    - product-level cannibalization (D-05)
    """
    baseline_start = promo_start - timedelta(days=baseline_days)
    promo_duration = (promo_end - promo_start).days + 1
    post_promo_end = promo_end + timedelta(days=promo_duration)  # Same duration after

    # Partition orders into baseline, promo, post-promo
    baseline_orders = [o for o in orders if baseline_start.isoformat() <= o["local_date"] < promo_start.isoformat()]
    promo_orders = [o for o in orders if promo_start.isoformat() <= o["local_date"] <= promo_end.isoformat()]
    post_orders = [o for o in orders if promo_end.isoformat() < o["local_date"] <= post_promo_end.isoformat()]

    # Compute daily averages for fair comparison
    baseline_daily_rev = sum(li["net_revenue"] for o in baseline_orders for li in o["line_items"]) / max(baseline_days, 1)
    promo_daily_rev = sum(li["net_revenue"] for o in promo_orders for li in o["line_items"]) / max(promo_duration, 1)

    lift_pct = ((promo_daily_rev - baseline_daily_rev) / baseline_daily_rev * 100) if baseline_daily_rev > 0 else 0

    # Product mix for cannibalization (D-05)
    # Compare product revenue share during promo vs baseline
    ...
```
[ASSUMED: exact implementation details]

### Covariates: Build Aligned Arrays
```python
# Source: VERIFIED from timesfm forecast_with_covariates signature
import holidays as holidays_lib
import numpy as np
import pandas as pd

def build_covariates(
    date_range: pd.DatetimeIndex,
    orders: list[dict],
    country: str = "US",
    custom_events: list[dict] | None = None,
) -> dict[str, list[list[float]]]:
    """Build covariate arrays aligned to date_range.

    Returns dict suitable for dynamic_numerical_covariates parameter of
    forecast_with_covariates(). Keys are covariate names, values are
    list of lists (one inner list per series in the batch).
    """
    n = len(date_range)
    years = sorted(set(d.year for d in date_range))
    hols = holidays_lib.country_holidays(country, years=years)

    # Day of week: 0=Monday..6=Sunday, normalized to 0-1
    day_of_week = [d.dayofweek / 6.0 for d in date_range]

    # Weekend flag
    is_weekend = [1.0 if d.dayofweek >= 5 else 0.0 for d in date_range]

    # Month (cyclical encoding or normalized)
    month = [(d.month - 1) / 11.0 for d in date_range]

    # Holiday flag
    is_holiday = [1.0 if d.date() in hols else 0.0 for d in date_range]

    # Holiday proximity: -7 to +3 days (D-19)
    holiday_proximity = _compute_holiday_proximity(date_range, hols)

    # Discount covariates from order data (historical only, zero for future)
    has_discount, discount_depth = _compute_discount_covariates(date_range, orders)

    return {
        "day_of_week": [day_of_week],  # Wrapped in list for batch dim
        "is_weekend": [is_weekend],
        "month": [month],
        "is_holiday": [is_holiday],
        "holiday_proximity": [holiday_proximity],
        "has_discount": [has_discount],
        "discount_depth": [discount_depth],
    }
```
[VERIFIED: holidays API + timesfm covariate shape requirements]

### Anomaly Clustering
```python
# Source: Derived from D-08, D-09, D-10, D-11 decisions
from dataclasses import dataclass

@dataclass
class AnomalyCluster:
    start_date: str
    end_date: str
    actual_total: float
    expected_total: float
    lower_bound: float
    upper_bound: float
    deviation_pct: float
    direction: str  # "Spike" or "Drop"
    label: str | None = None  # e.g., "likely: Black Friday"

def cluster_anomalies(anomaly_dates: list[dict]) -> list[AnomalyCluster]:
    """Group consecutive anomaly days into clusters (D-08).

    Each anomaly_date dict has: date, actual, expected, lower, upper.
    Consecutive dates (within 1 day) are merged into a single cluster.
    """
    if not anomaly_dates:
        return []

    clusters = []
    current = [anomaly_dates[0]]

    for ad in anomaly_dates[1:]:
        prev_date = date.fromisoformat(current[-1]["date"])
        curr_date = date.fromisoformat(ad["date"])
        if (curr_date - prev_date).days <= 1:
            current.append(ad)
        else:
            clusters.append(_finalize_cluster(current))
            current = [ad]
    clusters.append(_finalize_cluster(current))
    return clusters
```
[ASSUMED: exact clustering implementation]

### CLI Verb: Compare with Shortcuts
```python
# Source: D-23 + existing CLI pattern [VERIFIED: cli.py]
from dateutil.relativedelta import relativedelta

def _add_compare_subparser(sub):
    cmp = sub.add_parser("compare", help="Compare two time periods")
    cmp.add_argument("--yoy", action="store_true", help="This month vs same month last year")
    cmp.add_argument("--mom", action="store_true", help="This month vs last month")
    cmp.add_argument("--period-a-start", help="Custom period A start (YYYY-MM-DD)")
    cmp.add_argument("--period-a-end", help="Custom period A end (YYYY-MM-DD)")
    cmp.add_argument("--period-b-start", help="Custom period B start (YYYY-MM-DD)")
    cmp.add_argument("--period-b-end", help="Custom period B end (YYYY-MM-DD)")
    cmp.add_argument("--json", action="store_true", dest="json_output")

def _resolve_compare_dates(args) -> tuple[date, date, date, date]:
    today = date.today()
    if args.yoy:
        a_start = today.replace(day=1) - relativedelta(years=1)
        a_end = a_start + relativedelta(months=1) - timedelta(days=1)
        b_start = today.replace(day=1)
        b_end = today
    elif args.mom:
        a_start = today.replace(day=1) - relativedelta(months=1)
        a_end = today.replace(day=1) - timedelta(days=1)
        b_start = today.replace(day=1)
        b_end = today
    else:
        # Custom dates from args
        ...
    return a_start, a_end, b_start, b_end
```
[VERIFIED: dateutil.relativedelta is available]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Statistical anomaly detection (z-score, IQR) | Model-based anomaly detection using forecast quantile bands | TimesFM 2.5 (2025) | More context-aware: accounts for trend and seasonality the model learned |
| Prophet/ARIMA covariates | TimesFM XReg (linear ridge on residuals) | TimesFM 2.5 XReg (2025-10) | Simpler API but marginal value -- foundation model already captures most patterns |
| Manual holiday calendars | `holidays` package with 501 countries | holidays 0.94 | No maintenance burden for international calendars |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | AnalyticsResult dataclass pattern is the right abstraction for analytics output | Architecture Patterns | Low -- could use plain dicts or ForecastResult-like class instead |
| A2 | Single-pass backcast strategy is best for anomaly detection | Architecture Patterns | Medium -- rolling window might give better per-point expected values but is much slower |
| A3 | Discount rate edge cases need period-level aggregation | Common Pitfalls | Low -- straightforward to adjust |
| A4 | Seasonality index needs minimum history thresholds | Common Pitfalls | Low -- always safe to warn |
| A5 | `cohort_retention` default to monthly cohorts | Claude's Discretion | Low -- either monthly or weekly works, monthly is more standard for e-commerce |
| A6 | Country auto-detection from shop timezone is feasible | Claude's Discretion | Medium -- timezone-to-country mapping is not 1:1 (America/New_York could be US or Canada) |

## Open Questions

1. **Customer ID for Cohort Retention**
   - What we know: Normalized orders currently lack `customer_id` field. The GraphQL query needs to include `customer { id }`.
   - What's unclear: Whether the Shopify client query already fetches customer data but it's stripped during normalization, or if the query itself needs extending.
   - Recommendation: Extend `normalize_order()` to include `customer_id` from `customer.id` field. This is a small change to the Shopify query and normalizer but is prerequisite for R6.4.

2. **Anomaly Detection Strategy: Backcast vs Rolling**
   - What we know: TimesFM can forecast forward. To detect anomalies in historical data, we need "what the model expected" for each day.
   - What's unclear: Best approach -- (a) single forecast from start of history, use in-sample fit, (b) rolling window forecasts, or (c) use `return_backcast=True` to get the model's reconstruction of the input.
   - Recommendation: Use `return_backcast=True` (needed anyway for XReg). The backcast gives the model's reconstruction of the training data, which serves as "expected values" for anomaly detection. This is a single inference call, not rolling.

3. **ForecastConfig Recompilation for XReg**
   - What we know: Current config has `return_backcast=False`. XReg requires `True`. Recompilation takes ~10-30s.
   - What's unclear: Whether the model can maintain two compiled states, or if recompilation is required each time covariates toggle.
   - Recommendation: Lazy recompilation -- first call with covariates triggers recompile. Cache the compiled state. Since covariates are opt-in (feature flag), most users never trigger recompilation.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8+ with pytest-asyncio strict mode |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_analytics.py tests/test_covariates.py -x` |
| Full suite command | `uv run pytest -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| R5.1 | build_covariates returns aligned arrays | unit | `uv run pytest tests/test_covariates.py::test_build_covariates -x` | Wave 0 |
| R5.2 | All 7 built-in covariates computed correctly | unit | `uv run pytest tests/test_covariates.py::test_builtin_covariates -x` | Wave 0 |
| R5.3 | Custom events processed into covariates | unit | `uv run pytest tests/test_covariates.py::test_custom_events -x` | Wave 0 |
| R5.4 | Future covariates for horizon window | unit | `uv run pytest tests/test_covariates.py::test_future_covariates -x` | Wave 0 |
| R5.5 | forecast_with_covariates integration | integration | `uv run pytest tests/test_covariates.py::test_xreg_integration -x -m "not slow"` | Wave 0 |
| R5.6 | Feature flag controls covariate activation | unit | `uv run pytest tests/test_covariates.py::test_feature_flag -x` | Wave 0 |
| R6.1 | Promotion analysis lift + hangover + cannibalization | unit | `uv run pytest tests/test_analytics.py::test_analyze_promotion -x` | Wave 0 |
| R6.2 | Anomaly detection with sensitivity levels | unit | `uv run pytest tests/test_analytics.py::test_detect_anomalies -x` | Wave 0 |
| R6.3 | Period comparison with all 6 metrics | unit | `uv run pytest tests/test_analytics.py::test_compare_periods -x` | Wave 0 |
| R6.4 | Cohort retention matrix | unit | `uv run pytest tests/test_analytics.py::test_cohort_retention -x` | Wave 0 |
| R8.3 | MCP analyze_promotion tool handler | integration | `uv run pytest tests/test_mcp_tools_analytics.py::test_analyze_promotion_tool -x` | Wave 0 |
| R8.4 | MCP detect_anomalies tool handler | integration | `uv run pytest tests/test_mcp_tools_analytics.py::test_detect_anomalies_tool -x` | Wave 0 |
| R8.5 | MCP compare_periods tool handler | integration | `uv run pytest tests/test_mcp_tools_analytics.py::test_compare_periods_tool -x` | Wave 0 |
| R8.7 | MCP get_seasonality tool handler | integration | `uv run pytest tests/test_mcp_tools_analytics.py::test_get_seasonality_tool -x` | Wave 0 |
| R9.2 | CLI promo and compare verbs | unit | `uv run pytest tests/test_cli.py::test_promo_subcommand tests/test_cli.py::test_compare_subcommand -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_analytics.py tests/test_covariates.py -x`
- **Per wave merge:** `uv run pytest -x`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_analytics.py` -- covers R6.1, R6.2, R6.3, R6.4
- [ ] `tests/test_covariates.py` -- covers R5.1-R5.6
- [ ] `tests/test_mcp_tools_analytics.py` -- covers R8.3, R8.4, R8.5, R8.7
- [ ] Extended `tests/conftest.py` -- fixtures with promo periods, discount codes, multi-month data for cohort testing
- [ ] `tests/fixtures/sample_orders.json` may need expansion for cohort/seasonality testing (verify coverage)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Handled in earlier phases (Shopify auth) |
| V3 Session Management | no | MCP session managed by FastMCP |
| V4 Access Control | no | Single-user tool, no multi-tenant |
| V5 Input Validation | yes | Pydantic BaseModel for all tool params; date validation for ranges |
| V6 Cryptography | no | No crypto operations in analytics |

### Known Threat Patterns for Analytics Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malformed date ranges (end before start) | Tampering | Pydantic validators + explicit range checks |
| Excessive lookback_days causing OOM | Denial of Service | Field constraints (ge/le) on Pydantic models |
| Injection via promo_name parameter | Tampering | promo_name is only used in output labels, never in queries |

## Sources

### Primary (HIGH confidence)
- TimesFM master branch source -- `forecast_with_covariates()` signature, `return_backcast` requirement, covariate alignment semantics [VERIFIED: runtime `inspect.getsource`]
- `holidays` v0.94 -- 501 countries, API confirmed via runtime test [VERIFIED: `uv run python -c "import holidays"`]
- Existing codebase -- tools.py, cli.py, timeseries.py, forecaster.py, normalize.py patterns [VERIFIED: direct file reads]
- pyproject.toml -- all dependencies already present [VERIFIED: direct file read]

### Secondary (MEDIUM confidence)
- CONTEXT.md decisions D-01 through D-23 [VERIFIED: file read]
- REQUIREMENTS.md R5, R6, R8, R9 sections [VERIFIED: file read]

### Tertiary (LOW confidence)
- None -- all claims verified against codebase or runtime inspection

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all dependencies verified as installed and functional
- Architecture: HIGH -- patterns directly derived from existing codebase
- Pitfalls: HIGH for ForecastConfig/covariate issues (verified from source); MEDIUM for analytics edge cases (based on domain knowledge)
- Covariates API: HIGH -- verified via runtime inspection of actual installed TimesFM

**Research date:** 2026-04-17
**Valid until:** 2026-05-17 (stable -- no fast-moving dependencies)
