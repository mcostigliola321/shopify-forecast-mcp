---
phase: 01-scaffold-config
plan: 02
subsystem: packaging
tags: [uv, pyproject, timesfm, pytorch, dependencies]
requires:
  - 01-scaffold-config/01
provides:
  - locked-dependency-set
  - timesfm-git-pin
  - pytorch-cpu-index-override
  - dev-extras
affects:
  - pyproject.toml
  - uv.lock
tech-stack:
  added:
    - uv 0.11.6
    - timesfm @ git f085b9079918092aa5e3917a4e135f87f91a7f03
    - torch 2.11.0 (CPU on Linux/Win, PyPI default on macOS)
    - mcp 1.27.0, httpx, pandas, numpy, pydantic, pydantic-settings, holidays, python-dateutil
    - pytest 9.0.3, pytest-asyncio 1.3.0, respx 0.23.1, ruff 0.15.10, mypy 1.20.1
  patterns:
    - PEP 735 dependency-groups + project.optional-dependencies dual-declared for dev
    - tool.uv.sources index override for torch (linux/win32 only)
    - hatch.metadata.allow-direct-references for git deps
key-files:
  created:
    - .planning/phases/01-scaffold-config/timesfm-sha.txt
    - uv.lock
  modified:
    - pyproject.toml
decisions:
  - "Pinned TimesFM 2.5 to live-verified master commit f085b9079918092aa5e3917a4e135f87f91a7f03 (TimesFM_2p5_200M_torch class confirmed present)"
  - "Added [dependency-groups].dev mirroring [project.optional-dependencies].dev because uv 0.11 requires PEP 735 groups for default-groups resolution"
  - "Enabled tool.hatch.metadata.allow-direct-references=true so hatchling accepts the git URL for timesfm"
metrics:
  duration_minutes: 12
  tasks_completed: 2
  files_changed: 3
completed: 2026-04-13
---

# Phase 01 Plan 02: Wire dependencies into pyproject.toml Summary

Pinned TimesFM 2.5 to live commit, declared the full runtime + dev dependency set in `pyproject.toml` with PyTorch CPU-wheel index override and a hatchling direct-reference allowance, then resolved a clean `uv.lock` and verified both console scripts execute their stub messages.

## Pinned TimesFM SHA (Phase 3 contract)

**`f085b9079918092aa5e3917a4e135f87f91a7f03`** (master HEAD as of 2026-04-13)

Verified live via `git ls-remote refs/heads/master`, then confirmed `TimesFM_2p5_200M_torch` exists in `src/timesfm/__init__.py` at that SHA via raw GitHub fetch. After install, `uv run python -c "import timesfm; print(hasattr(timesfm, 'TimesFM_2p5_200M_torch'))"` returns `True`.

Note: the installed package metadata still reports `timesfm==2.0.0` because upstream hasn't bumped `__version__` — the 2p5 class lives in the 2.0.x source tree on master. Do not rely on `pkg_version` to differentiate 2.0 vs 2.5; rely on the `TimesFM_2p5_200M_torch` symbol.

## Resolver quirks encountered

1. **`uv` not installed on the host machine.** Installed via the official user-local installer (`curl -LsSf https://astral.sh/uv/install.sh | sh`) into `~/.local/bin`. Logged as Rule 3 (blocking). Future sessions need `~/.local/bin` on `PATH`.
2. **`git-lfs` missing.** TimesFM repo uses git-lfs; without it, `uv sync` failed with `git-lfs filter-process: command not found` during `git reset --hard`. Installed via Homebrew (`brew install git-lfs`). Logged as Rule 3.
3. **`tool.uv.default-groups` requires PEP 735.** uv 0.11 errored: "Default group `dev` is not defined in the project's `dependency-groups` table". Added a `[dependency-groups].dev` block mirroring `[project.optional-dependencies].dev`. Both forms are kept so either `--extra dev` or default-groups works.
4. **Hatchling rejected the timesfm git URL.** `Dependency #10 cannot be a direct reference unless field tool.hatch.metadata.allow-direct-references is set to true`. Added `[tool.hatch.metadata] allow-direct-references = true`. Logged as Rule 3.
5. **macOS torch path.** As designed: the `[tool.uv.sources].torch` marker is `sys_platform == 'linux' or sys_platform == 'win32'`, so on this Apple Silicon host torch resolved through PyPI (`torch==2.11.0`). No CPU index used. Linux/Windows users will hit the explicit pytorch-cpu index. No changes needed.

## Verification evidence

- `uv sync`: resolved 72 packages, built `timesfm` from git, installed clean.
- `uv run shopify-forecast` → `shopify-forecast: not implemented (Phase 4)` exit 0.
- `uv run shopify-forecast-mcp` → `shopify-forecast-mcp: not implemented (Phase 4)` exit 0.
- `uv run python -c "import timesfm; print(hasattr(timesfm, 'TimesFM_2p5_200M_torch'))"` → `True`.
- Plan automated verify expression: `VERIFY_OK`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocker] Installed `uv` toolchain**
- Found during: Task 2 attempting `uv sync`
- Issue: `uv` not on PATH (`command not found`)
- Fix: Ran official installer to `~/.local/bin/uv` (v0.11.6)
- Files modified: none in repo
- Commit: n/a (host-level install)

**2. [Rule 3 - Blocker] Installed `git-lfs`**
- Found during: Task 2 first `uv sync` run
- Issue: TimesFM repo uses git-lfs; uv's `git reset --hard` aborted
- Fix: `brew install git-lfs`
- Files modified: none in repo
- Commit: n/a (host-level install)

**3. [Rule 3 - Blocker] Added `[dependency-groups].dev`**
- Found during: Task 2 second `uv sync` run
- Issue: `Default group dev (from tool.uv.default-groups) is not defined in the project's dependency-groups table`
- Fix: Mirrored dev list under PEP 735 `[dependency-groups]`
- Files modified: `pyproject.toml`
- Commit: 76d5938

**4. [Rule 3 - Blocker] Added `tool.hatch.metadata.allow-direct-references = true`**
- Found during: Task 2 third `uv sync` run (build editable phase)
- Issue: Hatchling refuses direct git URLs without the opt-in
- Fix: Added the metadata block
- Files modified: `pyproject.toml`
- Commit: 76d5938

### Deferred Items

Logged to `.planning/phases/01-scaffold-config/deferred-items.md`:
- Repo has no `.gitignore` — Plan 01-01 omitted it. `__pycache__/`, `.venv/`, future `.env` are untracked. Should be addressed in 01-03 or 01-04.
- Untracked `shopify-forecast-mcp-PRD.md` and `01-01-SUMMARY.md` predate this plan.

## Known Stubs

None introduced by this plan. (Console scripts already stub from 01-01 and stay that way until Phase 4 — by design.)

## Self-Check: PASSED

- FOUND: `.planning/phases/01-scaffold-config/timesfm-sha.txt` (40 bytes, no trailing newline)
- FOUND: `pyproject.toml` (modified)
- FOUND: `uv.lock`
- FOUND commit: `de523c1` (Task 1)
- FOUND commit: `76d5938` (Task 2)
- TimesFM_2p5_200M_torch import: True
- Both console scripts: exit 0 with stub message
