# TimesFM 2.5 Research

**Confidence:** HIGH (verified against google-research/timesfm master branch)

## Critical PRD corrections

| Area | PRD says | Reality |
|---|---|---|
| Install | `pip install timesfm` (implied) | **Not on PyPI for 2.5.** Latest PyPI is `timesfm==1.3.0` (only 1.0/2.0 checkpoints). The `TimesFM_2p5_200M_torch` class only exists on GitHub master. Use `timesfm @ git+https://github.com/google-research/timesfm.git@<sha>` with `[torch,xreg]` extras, pin to a commit SHA. |
| Device `mps` | Listed as supported | **Not natively supported.** Source only branches `cuda` vs `cpu`. On Apple Silicon, runs on CPU (still ~1–3s for 1024-context, 90-horizon). Drop `mps` from env vars or document as CPU fallback. |
| `xreg` API | Flat `dict[str, np.ndarray]` passed to `forecast()` | **Wrong method.** Use `forecast_with_covariates()` — separate signature. Defer XReg to Phase 2. |
| Quantile interpretation | "10 quantiles, 10th–90th" | Channels are `[mean, q10, q20, q30, q40, q50, q60, q70, q80, q90]` — channel 0 is **mean**, not q10. Index map matters for anomaly detection. |
| Python version | `3.11+` | Pin `>=3.11,<3.12` for safety with upstream constraints (master may evolve). |

## ForecastConfig (verified)

```python
@dataclasses.dataclass(frozen=True)
class ForecastConfig:
    max_context: int = 0
    max_horizon: int = 0
    normalize_inputs: bool = False
    window_size: int = 0              # NOT YET IMPLEMENTED — do not set
    per_core_batch_size: int = 1
    use_continuous_quantile_head: bool = False
    force_flip_invariance: bool = True   # default already True
    infer_is_positive: bool = True
    fix_quantile_crossing: bool = False
    return_backcast: bool = False
```

All PRD-named params are real. `max_context` zero-pads short inputs and truncates long ones (TimesFM handles zeros well — confirms PRD assumption).

## Quantile output shapes

```python
point_forecast, quantile_forecast = model.forecast(
    horizon=12,
    inputs=[series_a, series_b],   # list of 1D np arrays, variable length
)
point_forecast.shape      # (2, 12)       → (batch, horizon)
quantile_forecast.shape   # (2, 12, 10)   → (batch, horizon, [mean, q10..q90])
```

Max horizon with continuous quantile head: ~1000 steps.

## Batch forecasting

`model.forecast(horizon=H, inputs=[arr1, ..., arrN])` accepts a list — auto-chunked by `global_batch_size = per_core_batch_size × device_count`. Recommend ~32–64 per batch on CPU, 256+ on GPU.

## XReg / Covariates (Phase 2)

```python
def forecast_with_covariates(
    self,
    inputs: list[Sequence[float]],
    dynamic_numerical_covariates: dict[str, Sequence[Sequence[float]]] | None = None,
    dynamic_categorical_covariates: dict[str, Sequence[Sequence[Category]]] | None = None,
    static_numerical_covariates: dict[str, Sequence[float]] | None = None,
    static_categorical_covariates: dict[str, Sequence[Category]] | None = None,
    xreg_mode: XRegMode = "xreg + timesfm",
    normalize_xreg_target_per_input: bool = True,
    ridge: float = 0.0,
    max_rows_per_col: int = 0,
    force_on_cpu: bool = False,
): ...
```

Key facts:
- **Separate method** from `forecast()`.
- **Dynamic covariates span both history AND horizon** in one aligned sequence per series — do not split.
- Static covariates are one value per series.
- Implementation is **linear ridge regression** (`BatchedInContextXRegLinear`), not deep attention. Sets realistic expectations for what covariates can do.
- Returns `tuple[list[np.ndarray], list[np.ndarray]]` — list per series, not stacked.
- Requires `[xreg]` extra (likely scikit-learn / jax).

**Decision:** MVP uses `forecast()` only (univariate). The 200M model handles seasonality from the target series alone. XReg is just linear ridge — marginal value over the foundation model. Add behind a feature flag in Phase 2.

## Memory + cold start

- Weights: 200M params, ~400MB download (bf16/fp16 safetensors), ~800MB in fp32.
- Runtime: 1.5–2.5 GB RAM with `max_context=1024, max_horizon=256`, batch 1, CPU.
- Cold start: HF download (first run only) + `from_pretrained` (~5–15s) + `compile()` (~10–30s). Subsequent calls fast.
- **Singleton + lazy load at server startup is mandatory** (PRD already specifies).
- Set `torch.set_float32_matmul_precision("high")` in initialization.

## Reference quickstart (for `forecaster.py`)

```python
import torch, numpy as np, timesfm

torch.set_float32_matmul_precision("high")

model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(
    "google/timesfm-2.5-200m-pytorch"
)
model.compile(timesfm.ForecastConfig(
    max_context=1024,
    max_horizon=256,
    normalize_inputs=True,
    use_continuous_quantile_head=True,
    force_flip_invariance=True,
    infer_is_positive=True,
    fix_quantile_crossing=True,
))

point, quantile = model.forecast(horizon=90, inputs=[daily_revenue_np])
# point.shape    -> (1, 90)
# quantile.shape -> (1, 90, 10)
# Channels: [mean, q10, q20, q30, q40, q50, q60, q70, q80, q90]
```

Sine-wave sanity test: `np.sin(np.linspace(0, 20*np.pi, 500))`.

## Licensing & history

- Weights: **Apache-2.0** (HF model card). Compatible with MIT downstream.
- 2025-10-02: QKV matrices fused for speed — numerical results unchanged.
- 2025-10-29: XReg covariate support re-added for 2.5.
- API breaking change vs 2.0: `TimesFmHparams` / `TimesFmCheckpoint` are gone. Old tutorials don't apply.
- No `forecast_on_df` pandas helper in 2.5 — convert to numpy yourself.

## Open questions (defer to implementation)

1. XReg padding semantics when series have different context lengths.
2. Whether `compile()` must be re-run if `max_horizon` changes mid-session.
3. GPU benchmarks on consumer hardware (no published numbers).

## Sources

- https://github.com/google-research/timesfm (master)
- https://huggingface.co/google/timesfm-2.5-200m-pytorch
- `src/timesfm/configs.py`, `timesfm_2p5_torch.py`, `utils/xreg_lib.py` on master
