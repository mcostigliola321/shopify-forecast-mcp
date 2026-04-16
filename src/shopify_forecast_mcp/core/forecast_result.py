"""ForecastResult -- structured output from ForecastEngine.

Wraps raw numpy arrays into a dataclass with presentation methods
(``to_table``, ``summary``) for consumption by MCP tools and CLI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

# Channel layout for TimesFM 2.5 quantile output
# Index 0 = mean, 1-9 = q10..q90
QUANTILE_CHANNELS = ["mean", "q10", "q20", "q30", "q40", "q50", "q60", "q70", "q80", "q90"]

# Metrics that should be formatted as currency
CURRENCY_METRICS = {"revenue", "aov"}


def _fmt_value(value: float, metric: str = "revenue") -> str:
    """Format a numeric value for display."""
    if metric in CURRENCY_METRICS:
        return f"${value:,.0f}"
    return f"{value:,.0f}"


@dataclass
class ForecastResult:
    """Structured forecast output with presentation helpers.

    Attributes
    ----------
    point_forecast:
        Shape ``(horizon,)`` -- point estimate per step.
    quantile_forecast:
        Shape ``(horizon, 10)`` or ``None`` -- channels
        ``[mean, q10, q20, q30, q40, q50, q60, q70, q80, q90]``.
    dates:
        ISO date strings for each forecast step.
    confidence_bands:
        Convenience dict mapping channel names to 1-D arrays.
        Keys: ``"mean"``, ``"q10"`` ... ``"q90"``.
    metadata:
        Flexible dict -- metric, group, horizon, context_days, device, etc.
    """

    point_forecast: np.ndarray
    quantile_forecast: np.ndarray | None
    dates: list[str]
    confidence_bands: dict[str, np.ndarray] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_forecast(
        cls,
        point: np.ndarray,
        quantile: np.ndarray | None,
        start_date: str | pd.Timestamp,
        freq: str = "D",
        metric: str = "revenue",
        **meta: Any,
    ) -> ForecastResult:
        """Build a ForecastResult from raw ForecastEngine output.

        Parameters
        ----------
        point:
            Shape ``(batch, horizon)`` from ``ForecastEngine.forecast()``.
        quantile:
            Shape ``(batch, horizon, 10)`` or ``None``.
        start_date:
            First forecast date (day after last observation).
        freq:
            Pandas frequency string (``"D"``, ``"W"``, ``"ME"``).
        metric:
            Metric name for formatting (``"revenue"``, ``"orders"``, etc.).
        **meta:
            Additional metadata entries.
        """
        # Extract single series (index 0) from batch dimension
        point_1d = point[0] if point.ndim == 2 else point
        horizon = len(point_1d)

        quantile_1d: np.ndarray | None = None
        bands: dict[str, np.ndarray] = {}

        if quantile is not None:
            quantile_1d = quantile[0] if quantile.ndim == 3 else quantile
            for i, name in enumerate(QUANTILE_CHANNELS):
                bands[name] = quantile_1d[:, i]

        # Generate date labels
        date_range = pd.date_range(start=start_date, periods=horizon, freq=freq)
        date_strs = [d.strftime("%Y-%m-%d") for d in date_range]

        metadata = {
            "metric": metric,
            "horizon": horizon,
            "freq": freq,
            **meta,
        }

        return cls(
            point_forecast=point_1d,
            quantile_forecast=quantile_1d,
            dates=date_strs,
            confidence_bands=bands,
            metadata=metadata,
        )

    @property
    def _metric(self) -> str:
        return self.metadata.get("metric", "revenue")

    def to_table(self, period: str = "weekly") -> str:
        """Render a markdown table with aggregated projections and CI bands.

        Parameters
        ----------
        period:
            ``"weekly"`` (7-day buckets) or ``"monthly"`` (30-day buckets).
        """
        bucket_size = 7 if period == "weekly" else 30
        horizon = len(self.point_forecast)
        metric = self._metric

        has_bands = "q10" in self.confidence_bands and "q90" in self.confidence_bands

        rows: list[str] = []
        rows.append("| Period | Projected | Low (10%) | High (90%) |")
        rows.append("|--------|-----------|-----------|------------|")

        bucket_idx = 0
        for start in range(0, horizon, bucket_size):
            end = min(start + bucket_size, horizon)
            bucket_idx += 1

            projected = float(np.sum(self.point_forecast[start:end]))

            if has_bands:
                low = float(np.sum(self.confidence_bands["q10"][start:end]))
                high = float(np.sum(self.confidence_bands["q90"][start:end]))
            else:
                low = projected
                high = projected

            label = f"Week {bucket_idx}" if period == "weekly" else f"Month {bucket_idx}"
            rows.append(
                f"| {label} | {_fmt_value(projected, metric)} "
                f"| {_fmt_value(low, metric)} | {_fmt_value(high, metric)} |"
            )

        return "\n".join(rows)

    def summary(self, prior_period_value: float | None = None) -> str:
        """Return a natural-language summary of the forecast.

        Parameters
        ----------
        prior_period_value:
            If provided, a trend percentage is computed vs this value.
        """
        metric = self._metric
        horizon = len(self.point_forecast)
        total = float(np.sum(self.point_forecast))

        has_bands = "q10" in self.confidence_bands and "q90" in self.confidence_bands
        if has_bands:
            ci_low = float(np.sum(self.confidence_bands["q10"]))
            ci_high = float(np.sum(self.confidence_bands["q90"]))
            ci_part = f" (90% CI: {_fmt_value(ci_low, metric)}-{_fmt_value(ci_high, metric)})"
        else:
            ci_part = ""

        metric_label = metric.replace("_", " ").capitalize()
        parts = [
            f"{metric_label} is projected to be {_fmt_value(total, metric)} "
            f"over the next {horizon} days{ci_part}."
        ]

        if prior_period_value is not None and prior_period_value != 0:
            pct = (total - prior_period_value) / prior_period_value * 100
            sign = "+" if pct >= 0 else ""
            parts.append(f"Trend: {sign}{pct:.1f}% vs prior period.")

        return " ".join(parts)
