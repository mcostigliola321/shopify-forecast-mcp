---
phase: 7
slug: distribution-docs
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-19
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Populated from research `## Validation Architecture` section — planner fills task-level rows.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x (existing) + markdown/yaml linters (Wave 0 installs) + `twine check` + `uv build --check` |
| **Config file** | `pyproject.toml` (pytest config), `.github/workflows/ci.yml` (existing smoke), `.github/workflows/publish.yml` (new, Wave 2) |
| **Quick run command** | `uv run pytest -x -q tests/test_docs_completeness.py tests/test_workflow_structure.py` |
| **Full suite command** | `uv run pytest -x -q && uv build && twine check dist/*` |
| **Estimated runtime** | ~60-90 seconds (Docker build verification runs in CI on tag only, not per-task) |

---

## Sampling Rate

- **After every task commit:** Run the quick run command scoped to the file(s) the task touches
- **After every plan wave:** Run full suite including `uv build` + `twine check dist/*`
- **Before `/gsd-verify-work`:** Full suite green + manual rc1 dry-run completes all 4 legs
- **Max feedback latency:** 90 seconds for code/doc tasks; Docker/publish workflow tasks validated via CI dispatch (~5 min) because they only exercise meaningfully against real GitHub runners

---

## Per-Task Verification Map

*Planner fills this during plan generation — one row per task in every plan. Each row maps to a concrete automated check.*

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| _(planner populates)_ | | | | | | | | | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

From research §Validation Architecture — these infrastructure items MUST exist before downstream tasks can be verified:

- [ ] `tests/test_docs_completeness.py` — asserts required H2 headings exist in README/SETUP/TOOLS/ARCHITECTURE, checks for placeholder tokens (`TODO`, `XXX`, `[date]`), validates internal link targets resolve (covers R11.1–R11.5)
- [ ] `tests/test_workflow_structure.py` — YAML-parses `.github/workflows/publish.yml`, asserts `id-token: write`, asserts `packages: write`, asserts tag trigger pattern, asserts `waits-for-ci` gate step exists (covers R12.1, R12.4)
- [ ] `tests/test_changelog_structure.py` — parses `CHANGELOG.md`, asserts Keep-a-Changelog format, asserts `[0.1.0]` section exists with Added subsection populated (covers D-21)
- [ ] `tests/test_dockerfile_structure.py` — parses Dockerfile, asserts `python:3.11-slim` base, asserts multistage with model-bake stage conditional, asserts `HF_HOME=/opt/hf-cache` in final stage, asserts entrypoint points at `/app/entrypoint.sh` (covers R12.2, R12.3)
- [ ] `scripts/gen_tools_doc.py` — generates `docs/TOOLS.md` per-tool sections from Pydantic models in `src/shopify_forecast_mcp/mcp/tools.py` (ensures TOOLS.md stays in sync with code; covers R11.3 + D-15)
- [ ] Markdown lint: `markdownlint-cli2` via pre-commit hook (covers docs quality baseline)
- [ ] Mermaid syntax validation: `@mermaid-js/mermaid-cli` smoke check on code blocks extracted from ARCHITECTURE.md (covers D-14)
- [ ] Link check: `lycheeverse/lychee-action` in a scheduled/manual CI job (non-blocking alerts on doc link rot)

*If any of these are missing when the planner generates tasks, the planner MUST create them as Wave 0 tasks before any downstream wave can be verified.*

---

## Manual-Only Verifications

These behaviors cannot be validated in CI and require operator action — documented in the rc1 dry-run checklist:

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `uvx --prerelease=allow shopify-forecast-mcp@0.1.0rc1` resolves + launches on a fresh machine | R12.1 + rc1 leg (c) | Fresh-machine resolution depends on state outside CI (uv cache, host network, PyPI CDN). Must run on a clean VM / docker run `python:3.11-slim`. | (1) Spin up clean `python:3.11-slim` container, (2) run `uvx --prerelease=allow shopify-forecast-mcp@0.1.0rc1 --help`, (3) confirm exit 0 + help output. |
| Claude Desktop loads the MCP server via `uvx` config snippet | R11.5 + success criterion 1 | Claude Desktop is an external app; no CI hook. | (1) Copy the README/SETUP.md snippet into `claude_desktop_config.json`, (2) restart Claude Desktop, (3) ask "what does next month look like?" against a real shop, (4) verify markdown table renders with no stack traces. |
| Clone-to-running <5 minutes on a fresh laptop | Phase 7 success criterion 1 | Timing depends on network + host environment. Stopwatch-validated. | Record from `git clone` through first successful `uvx` invocation returning a forecast. Target: <5 min on a modern laptop with warm pip cache or cold network. |
| `docker run ghcr.io/omnialta/shopify-forecast-mcp:bundled --network=none` works | R12.3 + success criterion 2 | Requires pulling the real published image from GHCR, which is only available after rc1 push. | (1) `docker pull ghcr.io/omnialta/shopify-forecast-mcp:bundled-rc`, (2) `docker run --network=none --rm ...:bundled-rc mcp`, (3) confirm server starts + accepts an MCP initialize message over stdio (no network errors). |
| PyPI Trusted Publisher OIDC upload succeeds | R12.1 + rc1 leg (b) | Requires real tag push to real PyPI; no staging. Pre-registration (pending publisher) done by maintainer in PyPI UI. | (1) Push `v0.1.0-rc1` tag, (2) watch workflow succeed at `uv publish` step, (3) confirm pypi.org/project/shopify-forecast-mcp shows 0.1.0rc1 as pre-release. |
| GHCR package visibility flip to public post-first-push | R12.2 + release mechanics | GHCR defaults new packages to private on first push. No CI workaround — UI click. | After first successful Docker push, navigate to `github.com/omnialta/shopify-forecast-mcp/packages`, flip visibility to public on both `:latest-rc` and `:bundled-rc` packages. |
| README quick-start reproduces "what does next month look like?" flow | Phase 7 success criterion 4 | Requires Shopify credentials + Claude Desktop interaction. | Follow README quick-start literally (copy-paste snippets), ask the example question, confirm output matches expectations. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (test_docs_completeness.py, test_workflow_structure.py, test_changelog_structure.py, test_dockerfile_structure.py, scripts/gen_tools_doc.py)
- [ ] No watch-mode flags
- [ ] Feedback latency < 90s for code/doc tasks (CI-dispatched workflow tasks exempt up to 5 min)
- [ ] Manual verifications itemized in rc1 dry-run checklist (not just here)
- [ ] `nyquist_compliant: true` set in frontmatter after planner fills the verification map

**Approval:** pending
