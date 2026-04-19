# MCP Tools Reference

Auto-generated from `src/shopify_forecast_mcp/mcp/tools.py`.
Run `uv run python scripts/gen_tools_doc.py -o docs/TOOLS.md` to refresh.

> **Keeping in sync:** the Parameters tables are generated from Pydantic models via
> `scripts/gen_tools_doc.py`. The Sample prompts and Example output sections are
> hand-written. When tool schemas change, re-generate and re-merge.

## Tools

- [`forecast_revenue`](#forecast-revenue)
- [`forecast_demand`](#forecast-demand)
- [`analyze_promotion`](#analyze-promotion)
- [`detect_anomalies`](#detect-anomalies)
- [`compare_periods`](#compare-periods)
- [`compare_scenarios`](#compare-scenarios)
- [`get_seasonality`](#get-seasonality)


## `forecast_revenue` <a id="forecast-revenue"></a>

Forecast total store revenue over a future horizon using TimesFM 2.5.

Returns a markdown summary and table with point forecast and 80% confidence band (q10-q90).

### Parameters

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `horizon_days` | integer |  | `30` | Number of days to forecast into the future |
| `context_days` | integer |  | `365` | Days of historical data to use as context |
| `frequency` | `daily` │ `weekly` │ `monthly` |  | `"daily"` | Aggregation frequency for the forecast |
| `include_chart_data` | boolean |  | `False` | If true, append raw forecast values as a JSON block |
| `store` | string | null |  | `null` | Store domain or label (multi-store mode) |

### Sample prompts

- "What does next month look like?"
- "Give me a weekly-granularity revenue forecast for the next 12 weeks."

### Example output

```
## Revenue forecast -- next 30 days

**Point forecast:** $247,830 total revenue (2026-04-20 -> 2026-05-19)
**80% confidence band:** $211,450 - $289,100

| Date | Point | q10 | q90 |
|------|-------|-----|-----|
| 2026-04-20 | $8,240 | $7,050 | $9,620 |
| 2026-04-21 | $8,180 | $6,980 | $9,540 |
| ... | ... | ... | ... |
| 2026-05-19 | $9,110 | $7,730 | $10,720 |

**Summary:** Trend is mildly upward (+3.8% vs trailing 30d). Band width
suggests moderate uncertainty, consistent with a typical April-May period
(no major promos detected in context window).
```


## `forecast_demand` <a id="forecast-demand"></a>

Forecast demand by product, collection, or SKU using TimesFM 2.5.

Returns a ranked markdown table showing projected demand per group
with confidence bands. When group_value is 'all', forecasts the top N
groups by historical volume.

### Parameters

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `group_by` | `product` │ `collection` │ `sku` |  | `"product"` | Dimension to group demand by: product, collection, or sku |
| `group_value` | string |  | `"all"` | Specific group identifier to forecast, or 'all' for top N groups |
| `metric` | `units` │ `revenue` │ `orders` |  | `"units"` | Demand metric to forecast |
| `horizon_days` | integer |  | `30` | Days to forecast |
| `top_n` | integer |  | `10` | Number of top groups when group_value='all' |
| `lead_time_days` | integer |  | `14` | Lead time in days for reorder calculation (default: 14) |
| `safety_factor` | number |  | `1.2` | Safety factor for reorder qty (default: 1.2, i.e. 20% buffer) |
| `store` | string | null |  | `null` | Store domain or label (multi-store mode) |

### Sample prompts

- "Which products will sell the most next month?"
- "Which SKUs need to be reordered in the next 2 weeks?"

### Example output

```
## Demand forecast -- top 10 products, next 30 days

| Product | Projected units | Current inventory | Reorder? |
|---------|-----------------|-------------------|----------|
| The 7" Skateboard | 342 | 180 | YES (projected stockout ~day 16) |
| Minimal T-Shirt (M, Black) | 287 | 520 | no |
| Minimal T-Shirt (L, Black) | 241 | 65 | YES (projected stockout ~day 8) |
| ... | ... | ... | ... |

**Reorder alerts:** 2 SKUs projected to hit zero inventory within the
forecast window. Lead time not modeled -- adjust reorder quantities for
your supplier's turnaround.
```


## `analyze_promotion` <a id="analyze-promotion"></a>

Analyze a past promotion's impact vs baseline: revenue lift, order lift, AOV change, post-promo hangover, and product cannibalization.

### Parameters

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `promo_start` | string | ✓ | — | Promo start date (YYYY-MM-DD) |
| `promo_end` | string | ✓ | — | Promo end date (YYYY-MM-DD) |
| `promo_name` | string |  | `""` | Optional promo name for labeling |
| `baseline_days` | integer |  | `30` | Days before promo to use as baseline |
| `store` | string | null |  | `null` | Store domain or label (multi-store mode) |

### Sample prompts

- "How did Black Friday perform vs the baseline?"
- "Analyze our March 15-22 sale: lift, AOV change, and any hangover."

### Example output

```
## Promotion analysis -- 2025-11-24 to 2025-11-30 ("Black Friday 2025")

| Metric | Promo period | Baseline (prior 30d avg) | Change |
|--------|--------------|--------------------------|--------|
| Revenue | $412,500 | $68,200/day x 7 = $477,400 | **-13.6%** (vs flat scaling baseline) |
| Revenue lift vs forecast | +$156,300 | -- | **+61% above forecast** |
| Orders | 2,847 | 1,760 | **+62%** |
| AOV | $145 | $179 | **-19%** (heavier discount basket) |
| Avg discount depth | 22.3% | 4.1% | -- |
| Hangover (post-promo 14d) | -$28,400 vs forecast | -- | **-11.7%** (mild hangover, recovered by day 12) |

**Summary:** Black Friday week pulled strong volume (+62% orders) at a
~19% AOV discount. Revenue lift vs forecast baseline was +61%.
Post-promo hangover was mild and short -- no meaningful cannibalization
of following month.
```


## `detect_anomalies` <a id="detect-anomalies"></a>

Detect anomalous days where actual values fell outside expected forecast bands.

### Parameters

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `lookback_days` | integer |  | `90` | Days to look back for anomalies |
| `sensitivity` | `low` │ `medium` │ `high` |  | `"medium"` | Anomaly sensitivity: low (q10/q90), medium (q20/q80), high (q30/q70) |
| `metric` | `revenue` │ `orders` │ `units` │ `aov` |  | `"revenue"` | Single metric to check for anomalies |
| `store` | string | null |  | `null` | Store domain or label (multi-store mode) |

### Sample prompts

- "Any anomalies in the last 90 days?"
- "Show me days when sales deviated significantly from the forecast."

### Example output

```
## Anomalies detected -- 2026-01-19 to 2026-04-19 (90 days)

**Sensitivity:** medium (q10/q90 bounds)

| Date | Actual | Expected | Bound breached | Deviation | Direction |
|------|--------|----------|----------------|-----------|-----------|
| 2026-02-14 | $21,400 | $8,900 | q90 ($12,100) | +140% | up-spike |
| 2026-03-07 | $780 | $7,200 | q10 ($5,400) | -89% | down-anomaly |
| 2026-04-03 | $18,200 | $8,750 | q90 ($11,600) | +108% | up-spike |

**Summary:** 3 anomalies flagged. Feb 14 and Apr 3 spikes coincide with
promo windows -- likely expected. Mar 7 dip warrants investigation
(storewide outage? data issue? competitor event?).
```


## `compare_periods` <a id="compare-periods"></a>

Compare two time periods across revenue, orders, units, AOV, discount rate, and units per order.

### Parameters

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `period_a_start` | string | ✓ | — | Period A start (YYYY-MM-DD) |
| `period_a_end` | string | ✓ | — | Period A end (YYYY-MM-DD) |
| `period_b_start` | string | ✓ | — | Period B start (YYYY-MM-DD) |
| `period_b_end` | string | ✓ | — | Period B end (YYYY-MM-DD) |
| `metrics` | array[string] | null |  | `null` | Metrics to compare (default: all 6) |
| `group_by` | string | null |  | `null` | Optional: product_id, collection_id, or sku |
| `store` | string | null |  | `null` | Store domain or label (multi-store mode) |

### Sample prompts

- "Compare Q1 2026 to Q1 2025."
- "How did November-December 2025 perform vs the same period last year?"

### Example output

```
## Period comparison

**Period A:** 2024-11-01 -> 2024-12-31 (61 days)
**Period B:** 2025-11-01 -> 2025-12-31 (61 days)

| Metric | Period A | Period B | Change |
|--------|----------|----------|--------|
| Revenue | $1,847,000 | $2,134,000 | **+15.5%** |
| Orders | 12,420 | 14,780 | **+19.0%** |
| AOV | $148.70 | $144.40 | **-2.9%** |
| Units | 18,910 | 22,530 | **+19.1%** |

**Summary:** YoY revenue up 15.5% driven by 19% more orders at slightly
lower AOV -- consistent with a successful promo strategy. Period B
outperformed forecast by 4.2%.
```


## `compare_scenarios` <a id="compare-scenarios"></a>

Compare 2-4 promotional scenarios with what-if forecasting.

Each scenario specifies a promo period and discount depth. Returns a
side-by-side markdown table with revenue projections, confidence bands,
and a recommendation for the best-performing scenario.

### Parameters

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `scenarios` | array[any] | ✓ | — | 2-4 named scenarios |
| `horizon_days` | integer |  | `30` | Days to forecast |
| `context_days` | integer |  | `365` | Days of historical data |
| `country` | string |  | `"US"` | Country for holiday covariates |
| `store` | string | null |  | `null` | Store domain or label (multi-store mode) |

### Sample prompts

- "Compare 3 promo scenarios for December: 10% off, 20% off + free shipping, and BOGO."
- "What if we ran a 15% off promo from 2026-05-25 to 2026-05-29 vs not running one at all?"

### Example output

```
## Scenario comparison -- 2026-05-25 to 2026-05-29

| Scenario | Discount | Projected revenue | Projected units | Lift vs baseline |
|----------|----------|-------------------|-----------------|------------------|
| Baseline (no promo) | 0% | $82,400 | 590 | -- |
| 10% off storewide | 10% | $94,600 | 730 | **+14.8%** revenue, +23.7% units |
| 20% off + free shipping | 20% | $106,300 | 920 | **+29.0%** revenue, +55.9% units |
| BOGO (select SKUs) | effective ~25% | $98,100 | 1,040 | +19.1% revenue, +76.3% units |

**Recommendation:** "20% off + free shipping" maximizes projected
revenue lift but has the steepest margin cost. "10% off" is the safer
margin-preserving play if the goal is incremental revenue without
aggressive promo fatigue.
```


## `get_seasonality` <a id="get-seasonality"></a>

Identify seasonal patterns in store data by day of week, month, or quarter.

### Parameters

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `lookback_days` | integer |  | `365` | Days of history to analyze |
| `granularity` | `day_of_week` │ `monthly` │ `quarterly` |  | `"day_of_week"` | Seasonality granularity |
| `metric` | `revenue` │ `orders` │ `units` │ `aov` |  | `"revenue"` | Metric to analyze |
| `store` | string | null |  | `null` | Store domain or label (multi-store mode) |

### Sample prompts

- "What are our strongest days of the week?"
- "Show me the monthly seasonality pattern learned from the last 2 years."

### Example output

```
## Seasonality -- monthly pattern

**Lookback:** 730 days (2 years)

| Month | Index (100 = mean) | Interpretation |
|-------|--------------------|----------------|
| Jan | 72 | Post-holiday lull |
| Feb | 78 | -- |
| Mar | 95 | Ramp toward spring |
| Apr | 103 | -- |
| May | 108 | -- |
| Jun | 92 | Summer dip (per PROJECT pattern) |
| Jul | 88 | Summer dip continues |
| Aug | 94 | -- |
| Sep | 107 | Back-to-school / fall kickoff |
| Oct | 115 | -- |
| Nov | 152 | **Black Friday / Cyber Monday** |
| Dec | 138 | Holiday tail |

**Summary:** Strong holiday concentration (Nov-Dec index = 145 avg vs
mean 100). Summer dip is real and predictable. Plan inventory / promo
calendar accordingly.
```
