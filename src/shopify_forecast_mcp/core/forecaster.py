"""ForecastEngine -- singleton wrapper around Google TimesFM 2.5.

Loads the 200M-parameter foundation model once and exposes a
``forecast(series, horizon)`` method returning raw numpy arrays.
The model is downloaded from HuggingFace on first invocation (~400 MB).
"""

from __future__ import annotations

import logging
import os
from typing import ClassVar

import numpy as np
import torch

torch.set_float32_matmul_precision("high")

import timesfm  # noqa: E402 — must come after torch precision setting

from shopify_forecast_mcp.config import Settings

logger = logging.getLogger(__name__)

COVARIATES_DISCLAIMER = (
    "Note: Covariates provide marginal improvement over TimesFM's foundation model. "
    "Results with and without covariates may be similar."
)


class ForecastEngine:
    """Singleton TimesFM 2.5 inference engine.

    Use the module-level :func:`get_engine` helper for convenience.
    """

    _instance: ClassVar[ForecastEngine | None] = None

    def __init__(self, settings: Settings | None = None) -> None:
        if settings is None:
            settings = Settings(
                shop="placeholder.myshopify.com",
                access_token="placeholder",  # type: ignore[arg-type]
            )

        # Device detection: cuda if available, else cpu. Never mps.
        requested = settings.timesfm_device.lower()
        if requested == "cuda" and torch.cuda.is_available():
            self.device = "cuda"
        elif requested == "mps":
            logger.warning(
                "MPS device requested but not supported by TimesFM 2.5 — "
                "falling back to CPU."
            )
            self.device = "cpu"
        else:
            if requested == "cuda" and not torch.cuda.is_available():
                logger.warning(
                    "CUDA device requested but not available — falling back to CPU."
                )
            self.device = "cpu"

        self.context_length: int = settings.timesfm_context_length
        self.default_horizon: int = settings.timesfm_horizon

        if settings.hf_home:
            os.environ["HF_HOME"] = settings.hf_home

        self._model: timesfm.TimesFM_2p5_200M_torch | None = None
        self._xreg_compiled: bool = False

    def _ensure_xreg_compiled(self) -> None:
        """Lazily recompile ForecastConfig with return_backcast=True for XReg."""
        if self._xreg_compiled:
            return

        self._model.compile(  # type: ignore[union-attr]
            timesfm.ForecastConfig(
                max_context=self.context_length,
                max_horizon=256,
                normalize_inputs=True,
                use_continuous_quantile_head=True,
                force_flip_invariance=True,
                infer_is_positive=True,
                fix_quantile_crossing=True,
                return_backcast=True,  # REQUIRED for XReg
            )
        )
        self._xreg_compiled = True
        logger.info("Recompiled ForecastConfig with return_backcast=True for XReg")

    def load(self) -> None:
        """Load the TimesFM model (downloads weights on first run)."""
        if self._model is not None:
            return

        logger.info("Downloading TimesFM 2.5 (~400MB, one-time)...")
        self._model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(
            "google/timesfm-2.5-200m-pytorch"
        )
        self._model.compile(
            timesfm.ForecastConfig(
                max_context=self.context_length,
                max_horizon=256,
                normalize_inputs=True,
                use_continuous_quantile_head=True,
                force_flip_invariance=True,
                infer_is_positive=True,
                fix_quantile_crossing=True,
            )
        )
        logger.info("TimesFM 2.5 loaded on %s", self.device)

    def forecast(
        self,
        series: np.ndarray | list[np.ndarray],
        horizon: int | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Run inference and return ``(point_forecast, quantile_forecast)``.

        Parameters
        ----------
        series:
            A single 1-D numpy array or a list of 1-D arrays (batch mode).
        horizon:
            Number of steps to forecast. Defaults to ``settings.timesfm_horizon``.

        Returns
        -------
        tuple[np.ndarray, np.ndarray]
            ``point_forecast`` with shape ``(batch, horizon)`` and
            ``quantile_forecast`` with shape ``(batch, horizon, 10)``.
            Quantile channels: ``[mean, q10, q20, q30, q40, q50, q60, q70, q80, q90]``.
        """
        self.load()

        if horizon is None:
            horizon = self.default_horizon

        if isinstance(series, np.ndarray):
            inputs = [series]
        else:
            inputs = series

        point, quantile = self._model.forecast(  # type: ignore[union-attr]
            horizon=horizon, inputs=inputs
        )
        return point, quantile

    def forecast_with_covariates(
        self,
        series: np.ndarray | list[np.ndarray],
        covariates: dict[str, list[list[float]]],
        horizon: int | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Run inference with external regressors (XReg covariates).

        Parameters
        ----------
        series:
            A single 1-D numpy array or a list of 1-D arrays (batch mode).
        covariates:
            Dict of covariate name -> ``[[values...]]`` from
            :func:`build_aligned_covariates`. Each array must have length
            ``len(input) + horizon``.
        horizon:
            Number of steps to forecast. Defaults to ``settings.timesfm_horizon``.

        Returns
        -------
        tuple[np.ndarray, np.ndarray]
            ``(point_forecast, quantile_forecast)`` same shape as :meth:`forecast`.
        """
        self.load()
        self._ensure_xreg_compiled()

        if horizon is None:
            horizon = self.default_horizon

        if isinstance(series, np.ndarray):
            inputs = [series]
        else:
            inputs = series

        # Validate covariate lengths (T-05-07)
        expected_len = len(inputs[0]) + horizon
        for name, values in covariates.items():
            if len(values[0]) != expected_len:
                msg = (
                    f"Covariate '{name}' length {len(values[0])} != "
                    f"expected {expected_len} (input_len={len(inputs[0])} + horizon={horizon})"
                )
                raise ValueError(msg)

        point, quantile = self._model.forecast_with_covariates(  # type: ignore[union-attr]
            inputs=inputs,
            dynamic_numerical_covariates=covariates,
            horizon=horizon,
        )
        return point, quantile


# ---------------------------------------------------------------------------
# Module-level singleton accessor
# ---------------------------------------------------------------------------

_engine: ForecastEngine | None = None


def get_engine(settings: Settings | None = None) -> ForecastEngine:
    """Return the singleton :class:`ForecastEngine`, creating it if needed."""
    global _engine  # noqa: PLW0603
    if _engine is None:
        _engine = ForecastEngine(settings)
    return _engine
