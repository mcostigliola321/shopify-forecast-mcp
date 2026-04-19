---
phase: 7
slug: distribution-docs
status: draft
nyquist_compliant: true
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

One row per task across Plans 01-05. Each row maps to a concrete automated check or — for manual-only verification — points to the rc1 checklist leg.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 07-01-T1 | 01 | 1 | R12.1, R12.4 | T-07-01, T-07-07 | No direct URL in wheel METADATA; PyPI-uploadable | build+metadata | `uv build && uvx --from twine twine check dist/* && ! unzip -p dist/*.whl '*/METADATA' \| grep -q 'git+https' && unzip -p dist/*.whl '*/METADATA' \| grep -q 'timecopilot-timesfm' && uv run pytest -x -q` | pyproject.toml, uv.lock | ⬜ pending |
| 07-01-T2 | 01 | 1 | R11.1-R11.4, R12.1-R12.4 | — | Wave 0 structural assertions available for downstream plans | pytest | `uv run pytest -x -q tests/test_workflow_structure.py tests/test_changelog_structure.py tests/test_dockerfile_structure.py tests/test_docs_completeness.py tests/test_claude_desktop_snippet.py` | tests/test_*.py (5 files) | ⬜ pending |
| 07-01-T3 | 01 | 1 | R11.3 | — | TOOLS.md generator emits 7 tool sections | CLI + grep | `uv run python scripts/gen_tools_doc.py \| head -1 \| grep -q '^# MCP Tools Reference' && uv run python scripts/gen_tools_doc.py \| grep -c '^## \`' \| grep -q '7'` | scripts/gen_tools_doc.py | ⬜ pending |
| 07-02-T1 | 02 | 2 | R12.1, R12.4 | T-07-02 | OIDC-only PyPI publish, no static tokens, CI gate | YAML parse + pytest | `python -c "import yaml,pathlib; d=yaml.safe_load(pathlib.Path('.github/workflows/publish.yml').read_text()); assert d['jobs']['publish-pypi']['permissions']['id-token']=='write'; assert d['jobs']['publish-pypi']['environment']['name']=='pypi'" && uv run pytest -x -q tests/test_workflow_structure.py -k "oidc or pypi or waits or no_static or tag"` | .github/workflows/publish.yml | ⬜ pending |
| 07-02-T2 | 02 | 2 | R12.2, R12.3 | T-07-05 | Multi-arch Docker + rc/stable tag discrimination + release creation | YAML parse + pytest | `python -c "import yaml,pathlib; d=yaml.safe_load(pathlib.Path('.github/workflows/publish.yml').read_text()); need={'wait-for-ci','build','publish-pypi','publish-docker','create-release'}; assert set(d['jobs'])>=need; assert d['jobs']['publish-docker']['permissions']['packages']=='write'" && uv run pytest -x -q tests/test_workflow_structure.py` | .github/workflows/publish.yml | ⬜ pending |
| 07-03-T1 | 03 | 2 | R12.2, R12.3 | T-07-11, T-07-12 | Non-root user, HF_HOME in both stages, JSON-array entrypoint | pytest + grep | `uv run pytest -x -q tests/test_dockerfile_structure.py -k "dockerfile and not entrypoint_script and not dockerignore"` | Dockerfile | ⬜ pending |
| 07-03-T2 | 03 | 2 | R12.2 | T-07-05, T-07-13 | Entrypoint dispatches whitelist of verbs; exec for SIGTERM; .dockerignore excludes sensitive paths | bash lint + pytest | `bash -n docker-entrypoint.sh && test -x docker-entrypoint.sh && uv run pytest -x -q tests/test_dockerfile_structure.py -k "entrypoint_script or dispatches or exec or dockerignore"` | docker-entrypoint.sh, .dockerignore | ⬜ pending |
| 07-04-T1 | 04 | 2 | R11.1, R11.5, D-21 | T-07-06 | README + CHANGELOG per D-16/D-21; no leaked credentials | pytest | `uv run pytest -x -q tests/test_docs_completeness.py::test_readme_exists tests/test_docs_completeness.py::test_readme_not_placeholder tests/test_docs_completeness.py::test_readme_has_alpha_banner tests/test_docs_completeness.py::test_readme_has_required_sections tests/test_docs_completeness.py::test_readme_shows_uvx_invocation tests/test_docs_completeness.py::test_readme_has_claude_desktop_snippet tests/test_changelog_structure.py tests/test_claude_desktop_snippet.py::test_readme_snippet_uses_uvx_command` | README.md, CHANGELOG.md, docs/images/.gitkeep | ⬜ pending |
| 07-04-T2 | 04 | 2 | R11.2, R11.4 | T-07-06, T-07-16 | SETUP.md covers scopes + install paths + env vars + multi-store; ARCHITECTURE.md has 3 mermaid diagrams | pytest | `uv run pytest -x -q tests/test_docs_completeness.py::test_setup_md_exists tests/test_docs_completeness.py::test_setup_covers_required_scopes tests/test_docs_completeness.py::test_setup_covers_both_install_paths tests/test_docs_completeness.py::test_setup_has_env_var_table tests/test_docs_completeness.py::test_architecture_md_exists tests/test_docs_completeness.py::test_architecture_has_three_mermaid_diagrams tests/test_docs_completeness.py::test_architecture_mentions_dual_backend tests/test_claude_desktop_snippet.py::test_claude_desktop_snippet_is_valid_json` | docs/SETUP.md, docs/ARCHITECTURE.md | ⬜ pending |
| 07-04-T3 | 04 | 2 | R11.3 | T-07-16, T-07-18 | TOOLS.md has 7 sections + sample prompts + example outputs | pytest + grep | `uv run pytest -x -q tests/test_docs_completeness.py::test_tools_md_exists tests/test_docs_completeness.py::test_tools_md_has_section_per_tool tests/test_docs_completeness.py::test_tools_md_has_per_tool_anchors tests/test_docs_completeness.py::test_no_placeholder_tokens_in_docs && test "$(grep -c '^## \`' docs/TOOLS.md)" = "7" && grep -q '### Sample prompts' docs/TOOLS.md && grep -q '### Example output' docs/TOOLS.md` | docs/TOOLS.md | ⬜ pending |
| 07-05-T1 | 05 | 3 | R12.1-R12.4 | T-07-03, T-07-19 | Release runbook with prereqs + 4-leg + rollback | grep | `test -f docs/RELEASE.md && test "$(wc -l < docs/RELEASE.md)" -gt 100 && grep -q "Trusted Publisher" docs/RELEASE.md && grep -q "v0.1.0-rc1" docs/RELEASE.md && grep -q "4-leg verification" docs/RELEASE.md` | docs/RELEASE.md | ⬜ pending |
| 07-05-T2 | 05 | 3 | R12.1 | T-07-02 | One-time PyPI + environment prereqs complete | **MANUAL** — rc1 checklist §"One-time prerequisites" legs 1-3 | manual; operator confirms in rc1 GitHub issue | — | ⬜ pending |
| 07-05-T3 | 05 | 3 | R11.5, R12.1-R12.3 | T-07-03, T-07-20 | rc1 dry-run 4 legs all green | **MANUAL** — rc1 checklist §"4-leg verification" | manual; operator records in rc1 GitHub issue with stopwatch time | — | ⬜ pending |
| 07-05-T4 | 05 | 3 | R11.5, R12.1-R12.5 | T-07-19, T-07-22 | v0.1.0 stable tag published; rc tags untouched; README banner retained | **MANUAL** + quick smoke | `curl -s https://pypi.org/pypi/shopify-forecast-mcp/json \| jq '.info.version'` returns `"0.1.0"`; `gh release list --limit 1` shows v0.1.0 without pre-release flag; manual checks per rc1 checklist | — | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

From research §Validation Architecture — these infrastructure items MUST exist before downstream tasks can be verified:

- [x] **Plan 01 Task 2 creates these:**
  - `tests/test_docs_completeness.py` — asserts required H2 headings exist in README/SETUP/TOOLS/ARCHITECTURE, checks for placeholder tokens (`TODO`, `XXX`, `[date]`), validates internal link targets resolve (covers R11.1–R11.5)
  - `tests/test_workflow_structure.py` — YAML-parses `.github/workflows/publish.yml`, asserts `id-token: write`, asserts `packages: write`, asserts tag trigger pattern, asserts `waits-for-ci` gate step exists (covers R12.1, R12.4)
  - `tests/test_changelog_structure.py` — parses `CHANGELOG.md`, asserts Keep-a-Changelog format, asserts `[0.1.0]` section exists with Added subsection populated (covers D-21)
  - `tests/test_dockerfile_structure.py` — parses Dockerfile, asserts `python:3.11-slim` base, asserts multistage with model-bake stage conditional, asserts `HF_HOME=/opt/hf-cache` in final stage, asserts entrypoint points at `/app/entrypoint.sh` (covers R12.2, R12.3)
  - `tests/test_claude_desktop_snippet.py` — extracts and json-parses the Claude Desktop config snippet from README/SETUP.md
- [x] **Plan 01 Task 3 creates:**
  - `scripts/gen_tools_doc.py` — generates `docs/TOOLS.md` per-tool sections from Pydantic models in `src/shopify_forecast_mcp/mcp/tools.py` (ensures TOOLS.md stays in sync with code; covers R11.3 + D-15)
- [ ] **Deferred to v0.2 (not blocking v0.1.0):** Markdown lint `markdownlint-cli2` pre-commit hook; Mermaid syntax validation via `@mermaid-js/mermaid-cli`; Link check via `lycheeverse/lychee-action`. These are quality baselines but not required for v0.1.0 per RESEARCH §Validation Architecture "Wave 0 Gaps".

---

## Manual-Only Verifications

These behaviors cannot be validated in CI and require operator action — documented in the rc1 dry-run checklist (`docs/RELEASE.md` §"4-leg verification"):

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

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (manual-only tasks — 07-05-T2, T3, T4 — are explicitly flagged as MANUAL above with reference to the rc1 runbook)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (rc1 manual checkpoints in Plan 05 are separated by Task 1's automated `docs/RELEASE.md` check)
- [x] Wave 0 covers all MISSING references (test_docs_completeness.py, test_workflow_structure.py, test_changelog_structure.py, test_dockerfile_structure.py, test_claude_desktop_snippet.py, scripts/gen_tools_doc.py)
- [x] No watch-mode flags
- [x] Feedback latency < 90s for code/doc tasks (CI-dispatched workflow tasks exempt up to 5 min)
- [x] Manual verifications itemized in rc1 dry-run checklist (docs/RELEASE.md — created in Plan 05 Task 1)
- [x] `nyquist_compliant: true` set in frontmatter after planner fills the verification map

**Approval:** approved by planner 2026-04-19
