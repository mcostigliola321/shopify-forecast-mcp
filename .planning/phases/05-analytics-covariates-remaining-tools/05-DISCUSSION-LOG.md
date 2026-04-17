# Phase 5: Analytics, Covariates & Remaining Tools - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-17
**Phase:** 05-analytics-covariates-remaining-tools
**Areas discussed:** Analytics output design, Anomaly detection tuning, Covariate scope & defaults, CLI verb design

---

## Analytics Output Design

| Option | Description | Selected |
|--------|-------------|----------|
| Table + summary | Each tool returns markdown table + 2-3 sentence summary | ✓ |
| Table only | Just data table, let LLM interpret | |
| Rich narrative + table | Lead with narrative paragraph, then table | |

**User's choice:** Table + summary
**Notes:** Consistent with Phase 4 forecast tools pattern.

---

| Option | Description | Selected |
|--------|-------------|----------|
| Findings + light recs | Report data + 1-2 actionable suggestions | ✓ |
| Findings only | Just numbers and observations | |
| You decide | Claude's discretion | |

**User's choice:** Findings + light recs

---

| Option | Description | Selected |
|--------|-------------|----------|
| All six with highlight | Revenue, orders, units, AOV, discount_rate, units_per_order — bold biggest movers | ✓ |
| All six no highlight | Show all, no emphasis | |
| User-specified only | Only show requested metrics | |

**User's choice:** All six with highlight
**Notes:** discount_rate and units_per_order were folded in from user suggestion during discussion. User asked about conversion rate (mobile/desktop) but this was deferred — requires session data from different API.

---

| Option | Description | Selected |
|--------|-------------|----------|
| Separate hangover section | Dedicated "Post-Promo Impact" section after lift table | ✓ |
| Inline in summary | Mention in natural-language summary only | |
| You decide | Claude's discretion | |

**User's choice:** Separate hangover section

---

| Option | Description | Selected |
|--------|-------------|----------|
| Index table | Rows = day/month, column = index (100=avg) | ✓ |
| Sparkline ASCII | ASCII bar chart alongside rows | |
| Both | Index + ASCII bars | |

**User's choice:** Index table

---

| Option | Description | Selected |
|--------|-------------|----------|
| Full matrix + summary | Complete cohort × period matrix + summary line with avg retention and LTV | ✓ |
| Summary only | Key stats: avg retention at 30/60/90d, LTV | |
| Adaptive | Full if <12 cohorts, summary if more | |

**User's choice:** Full matrix + summary

---

| Option | Description | Selected |
|--------|-------------|----------|
| Product-level shift | Compare product mix during promo vs baseline, flag cannibalized products | ✓ |
| Simple revenue shift | Just compare total revenue trajectory post-promo | |
| Skip cannibalization | Too speculative | |

**User's choice:** Product-level shift

---

| Option | Description | Selected |
|--------|-------------|----------|
| Anomaly list + forecast context | Each row: date, actual, expected, band, deviation % | ✓ |
| Anomaly list only | Just date + actual + direction | |
| You decide | Claude's discretion | |

**User's choice:** Anomaly list + forecast context

---

## Anomaly Detection Tuning

| Option | Description | Selected |
|--------|-------------|----------|
| Quantile band based | Low=q10/q90, Medium=q20/q80, High=q30/q70 | ✓ |
| Z-score based | Low=3σ, Medium=2σ, High=1.5σ | |
| Hybrid | Both must agree for "confirmed" | |

**User's choice:** Quantile band based

---

| Option | Description | Selected |
|--------|-------------|----------|
| Warn and proceed | Run with warning if <90 days | ✓ |
| Minimum threshold | Error if <90 days | |
| Adaptive sensitivity | Auto-lower sensitivity for short histories | |

**User's choice:** Warn and proceed

---

| Option | Description | Selected |
|--------|-------------|----------|
| Grouped clusters | Consecutive anomaly days = one event with start/end | ✓ |
| Individual days | Every anomalous day its own row | |
| Both views | Grouped summary + day-by-day detail | |

**User's choice:** Grouped clusters

---

| Option | Description | Selected |
|--------|-------------|----------|
| Label known events | Tag anomalies overlapping holidays/promos | ✓ |
| No labeling | Just report anomaly, user correlates | |
| You decide | Claude's discretion | |

**User's choice:** Label known events

---

| Option | Description | Selected |
|--------|-------------|----------|
| Spike/Drop with magnitude | "Spike (+42% above expected)" or "Drop (-31%)" | ✓ |
| Just deviation % | Show % number only | |

**User's choice:** Spike/Drop with magnitude

---

| Option | Description | Selected |
|--------|-------------|----------|
| Single metric per call | One metric at a time, consistent with forecast tools | ✓ |
| Multiple metrics | Accept list of metrics | |
| You decide | Claude's discretion | |

**User's choice:** Single metric per call

---

| Option | Description | Selected |
|--------|-------------|----------|
| 90 days + auto-clamp | Default 90d, reduce to available, warn if <90d | ✓ |
| 180 days | | |
| 365 days | | |

**User's choice:** 90 days + auto-clamp
**Notes:** User asked about CLI-only users with 60-day history. Confirmed CLI backend doesn't impose 60d limit (that's read_orders scope without read_all_orders). Auto-clamp handles edge cases cleanly.

---

## Covariate Scope & Defaults

| Option | Description | Selected |
|--------|-------------|----------|
| All built-in by default | When enabled: all covariates activate | ✓ |
| Calendar only | Only time-based covariates by default | |
| Let user pick | Cherry-pick individual covariates | |

**User's choice:** All built-in by default

---

| Option | Description | Selected |
|--------|-------------|----------|
| Fixed -7/+3 | Hardcoded holiday_proximity window | ✓ |
| Configurable | Add before/after params | |

**User's choice:** Fixed -7/+3

---

| Option | Description | Selected |
|--------|-------------|----------|
| Always show disclaimer | Append marginal value note when covariates enabled | ✓ |
| Show only if minimal delta | Compare internally, show if <5% difference | |
| Document only | Put in docs, not in output | |

**User's choice:** Always show disclaimer

---

## CLI Verb Design

| Option | Description | Selected |
|--------|-------------|----------|
| Explicit dates | `--start DATE --end DATE --name NAME` | ✓ |
| Named presets + custom | Built-in presets like --preset black-friday | |
| Relative dates | `--start -30d --end -23d` | |

**User's choice:** Explicit dates

---

| Option | Description | Selected |
|--------|-------------|----------|
| Markdown default, --json flag | Human-readable markdown + --json for piping | ✓ |
| Plain text default | Simpler table without markdown | |
| You decide | Match Phase 4 CLI | |

**User's choice:** Markdown default, --json flag

---

| Option | Description | Selected |
|--------|-------------|----------|
| Shortcuts + custom | --yoy, --mom shortcuts + custom date ranges | ✓ |
| Custom dates only | Always explicit start/end for both periods | |
| You decide | Claude's discretion | |

**User's choice:** Shortcuts + custom

---

## Claude's Discretion

- Exact markdown table column ordering and formatting
- Error message wording for invalid date ranges, missing data
- cohort_retention default cohort period (monthly vs weekly)
- Internal module organization of analytics.py
- Custom events API shape for covariates
- Country auto-detection from shop timezone vs explicit param

## Deferred Ideas

- Conversion rate (mobile/desktop) — requires Shopify Analytics API + read_analytics scope
- Product mix shift analysis
- Repeat vs new customer segmentation
- Revenue concentration / Pareto analysis
- Refund rate trending by product
