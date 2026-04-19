---
phase: 07-distribution-docs
plan: 04
subsystem: documentation
tags: [documentation, mermaid, onboarding, changelog, merchant-first]

# Dependency graph
requires:
  - phase: 07-distribution-docs/07-01
    provides: scripts/gen_tools_doc.py, tests/test_docs_completeness.py, tests/test_changelog_structure.py, tests/test_claude_desktop_snippet.py
  - phase: 04-mcp-server-cli-mvp
    provides: src/shopify_forecast_mcp/mcp/tools.py (7 Pydantic ParamsModels — source for TOOLS.md)
  - phase: 04.1-shopify-cli-toolkit-integration
    provides: dual-backend design (DirectBackend + CliBackend) — source for ARCHITECTURE.md
  - phase: 05-analytics-covariates-remaining-tools
    provides: analyze_promotion/detect_anomalies/compare_periods/get_seasonality semantics
  - phase: 06-advanced-tools
    provides: compare_scenarios + reorder alerts + multi-store config shape
provides:
  - README.md — merchant-first landing page (D-16 locked structure, 179 lines, 7.5KB)
  - CHANGELOG.md — Keep-a-Changelog 1.1.0 format with seeded [0.1.0] entry (D-21)
  - docs/SETUP.md — install walkthrough covering 4 required scopes + both install paths + multi-store (D-17, 321 lines)
  - docs/ARCHITECTURE.md — 3 Mermaid diagrams + 14-row key decisions table (D-14, 153 lines)
  - docs/TOOLS.md — 7-tool reference with generated Parameters tables + hand-written prompts/outputs (D-15, 311 lines)
  - docs/images/.gitkeep — reserved for SETUP.md screenshots captured during rc1 walkthrough
affects: [07-02 publish-pipeline (CHANGELOG feeds release body), 07-05 release-cut (README alpha banner + SETUP quick-start are the 5-min success criterion)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Generated-then-enriched doc: scripts/gen_tools_doc.py emits Parameters tables from Pydantic schemas; Sample prompts + Example outputs are hand-written and merged manually when schemas change."
    - "Merchant-first README voice per D-12 (merchant-operator primary reader; developer call-outs explicit)."
    - "Mermaid diagrams live in ARCHITECTURE.md only (not README) — PyPI's CommonMark renderer doesn't render mermaid so keeping diagrams in docs/ prevents a broken PyPI landing page (RESEARCH Pitfall 7)."

key-files:
  created:
    - README.md (full rewrite from 337-byte placeholder; 7526 bytes)
    - CHANGELOG.md (4216 bytes)
    - docs/SETUP.md (11287 bytes)
    - docs/ARCHITECTURE.md (7392 bytes)
    - docs/TOOLS.md (11990 bytes)
    - docs/images/.gitkeep (0 bytes — directory placeholder)
  modified: []

key-decisions:
  - "Kept mermaid out of README per Pitfall 7 — PyPI renders README as CommonMark and would show mermaid blocks as raw code. Architecture summary prose + deep link to ARCHITECTURE.md is the cleaner UX for PyPI visitors."
  - "Included an inline CLI sanity-check tip in README Quick start (`uvx shopify-forecast-mcp` bare invocation) — satisfies the test_readme_shows_uvx_invocation literal string check AND gives merchants a pre-Claude-Desktop confidence smoke test."
  - "Example outputs in TOOLS.md are synthesized (marker-quoted fenced blocks) — they represent expected shape, not captured fixtures. Drift risk (T-07-18) is accepted for v0.1.0; Plan 5 rc1 walkthrough will catch gross mismatches. Live-captured outputs are a v0.2 improvement."
  - "Removed a nested `'env': {...}` inline from SETUP.md pre-release section to keep _every_ ```json fenced block valid JSON — test_claude_desktop_snippet_is_valid_json is parameterized across both README and SETUP and extracts the FIRST json block; a partially-rendered block would have broken the test even though other blocks below are fine. Restructured the pre-release docs to show the args array as a shell comment instead."

requirements-completed: [R11.1, R11.2, R11.3, R11.4, R11.5, R12.5]

# Metrics
duration: ~7min
completed: 2026-04-19
---

# Phase 07 Plan 04: Documentation Suite Summary

**Wrote the full v0.1.0 documentation suite (README, CHANGELOG, SETUP, ARCHITECTURE with 3 Mermaid diagrams, TOOLS for all 7 MCP tools) — satisfying R11.1-R11.5 and enabling the <5-minute clone-to-running success criterion for the Phase 7 release.**

## Performance

- **Duration:** ~7 min
- **Started:** 2026-04-19T17:51:23Z
- **Completed:** 2026-04-19T17:58:44Z
- **Tasks:** 3/3 completed
- **Files created:** 6 (5 documentation files + 1 directory placeholder)

## Accomplishments

- **Full README rewrite** from a 337-byte scaffold placeholder to a 179-line / 7.5KB merchant-first landing page per D-16 locked structure: alpha banner, Why, 3-step Quick start, 4 conversation examples, anchor-linked Tools table, Architecture summary, Configuration, CLI, Docker, Roadmap, Contributing, License.
- **CHANGELOG.md seeded** with Keep-a-Changelog 1.1.0 format — `[Unreleased]` placeholder + fully populated `[0.1.0] - 2026-04-19` with 27 bullet points under `### Added` covering the 7 MCP tools by name, 4 CLI verbs, dual-backend architecture, multi-store support, covariate engineering, Docker images, Trusted Publisher OIDC, and the full doc suite. Separate `### Changed` section documents the TimesFM fork swap (D-23 rationale). `### Known Limitations` lists the 5 things a merchant would reasonably hit (mps, Docker OAuth, first-run latency, 3.11 pin, alpha API surface).
- **SETUP.md covers everything a merchant needs** — all 4 required Shopify scopes verbatim, both install paths (uvx + Docker), 3 MCP client walkthroughs (Claude Desktop, Claude Code, generic), complete 14-row env var reference, multi-store nested-env config, CLI for all 4 verbs + `auth`, and a 6-entry troubleshooting section.
- **ARCHITECTURE.md hits the D-14 three-diagram contract** — two-layer architecture (client/frontends/core/external subgraphs), data flow pipeline (Shopify GraphQL → ForecastResult → markdown), and dual-backend selection tree (create_backend decision logic). 14-row key decisions table references the D-23 TimesFM fork rationale.
- **TOOLS.md generated-then-enriched** — `scripts/gen_tools_doc.py` produced the 7 Parameters tables from Pydantic schemas; each tool section was then appended with 2 merchant-voice sample prompts and 1 fully-rendered markdown example output. Top-of-file sync comment documents the regenerate-then-remerge workflow.
- **All 28 documentation assertions pass** — `tests/test_docs_completeness.py` (17), `tests/test_changelog_structure.py` (8), `tests/test_claude_desktop_snippet.py` (3) — zero skips across the doc surface this plan ships.

## Task Commits

Each task was committed atomically:

1. **Task 1: Write README.md + CHANGELOG.md + docs/images/.gitkeep** — `a1caea2` (docs)
2. **Task 2: Write docs/SETUP.md + docs/ARCHITECTURE.md (3 Mermaid diagrams)** — `9de0a4e` (docs)
3. **Task 3: Generate + enrich docs/TOOLS.md (7-tool reference)** — `b5842b7` (docs)

## File Metrics

| File | Lines | Words | Bytes |
|------|-------|-------|-------|
| `README.md` | 179 | 925 | 7,526 |
| `CHANGELOG.md` | 51 | 515 | 4,216 |
| `docs/SETUP.md` | 321 | 1,343 | 11,287 |
| `docs/ARCHITECTURE.md` | 153 | 892 | 7,392 |
| `docs/TOOLS.md` | 311 | 1,956 | 11,990 |
| **Total** | **1,015** | **5,631** | **42,411** |

Against acceptance minimums (README >2KB, SETUP >80 lines, ARCHITECTURE >60 lines, TOOLS >200 lines): all five exceed their floor by 2-5x. Well-sized for the "clone-to-running in <5 min" target — a merchant reads the first ~120 lines of README (landing through Quick start), copies one JSON snippet, and ships.

## Structural Invariants Verified

- **Mermaid diagrams in ARCHITECTURE.md:** 3 (target: ≥3). `grep -c '^```mermaid' docs/ARCHITECTURE.md` = 3.
- **Tool sections in TOOLS.md:** exactly 7 (target: 7). `grep -c '^## \`' docs/TOOLS.md` = 7.
- **JSON snippet parseability:** 4/4 fenced ```json blocks parse cleanly (1 in README, 3 in SETUP). Python inline validation confirmed all 4 are round-trippable.
- **CHANGELOG [0.1.0] extraction smoke test:** `awk 'BEGIN{f=0} /^## \[0\.1\.0\]/{f=1; next} /^## \[/ && f==1 {f=0} f==1' CHANGELOG.md` emits 42 lines with 27 bullet-point entries under Added. `ffurrer2/extract-release-notes@v3` (used in Plan 02 publish workflow) will have non-empty substantive content to inject into the GitHub Release body.
- **Placeholder hygiene:** zero `TODO`/`XXX`/`FIXME`/`[TBD]`/`[date]` tokens outside fenced code blocks in any of the 5 doc files.
- **Anchor-link consistency:** README Tools table uses hyphen-form anchors (`docs/TOOLS.md#forecast-revenue`); TOOLS.md top-of-file index + per-section `<a id="...">` tags use the same hyphen form — verified by `test_tools_md_has_per_tool_anchors`.

## Decisions Made

- **Added an inline CLI sanity-check tip in README Quick start** — the verification test `test_readme_shows_uvx_invocation` requires the literal string `uvx shopify-forecast-mcp` (with a space between `uvx` and the package). The primary install path sits inside a JSON args array (`"args": ["shopify-forecast-mcp"]`), which doesn't contain that literal. Rather than weaken the test or force-duplicate the JSON snippet, I added a blockquote callout after Step 3: *"Prefer the terminal first? You can verify your setup before wiring Claude Desktop by running `uvx shopify-forecast-mcp` directly..."* This doubles as a great pre-Claude confidence check for merchants.
- **Kept mermaid out of README entirely** (Pitfall 7 from RESEARCH). README has a prose architecture summary + link to ARCHITECTURE.md where the 3 diagrams live. GitHub renders mermaid in README; PyPI does not. This choice makes the PyPI landing page clean while GitHub visitors can still click through.
- **Pre-release docs pattern in SETUP.md** — originally planned to show a Claude Desktop config for the rc1 case with `"env": { ... }` as a literal placeholder. That would have made the second json block in SETUP.md fail `json.loads()` (mid-object placeholder is not valid JSON). Restructured to show the bare `--prerelease=allow` CLI invocation + a shell-comment explaining how to translate it into the Claude Desktop `args` array. All 3 SETUP.md json blocks now parse cleanly.
- **TOOLS.md character discipline** — replaced `→` / `—` / `⚠️` / `↑` / `↓` inside rendered code blocks with ASCII equivalents (`->`, `--`, `YES`, `up-spike`, `down-anomaly`) to sidestep any edge case with consoles/terminals that don't render the unicode. Kept markdown-rendered headings and prose using normal unicode.
- **`forecast_demand` example output** — plan draft used `⚠️ YES` in the Reorder column; switched to bare `YES` per the character-discipline rule above. Plan acceptance criteria don't reference the warning glyph.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Restructured SETUP.md pre-release section to keep all json blocks valid**

- **Found during:** Task 2, running `test_claude_desktop_snippet_is_valid_json` parameterized over `[README, SETUP]`.
- **Issue:** Plan action spec showed the pre-release Claude Desktop config as `"env": { ... }` with a literal `{ ... }` placeholder. That's invalid JSON. The test extracts the first ```json fenced block from each file and calls `json.loads()` on it. For SETUP.md that would have been the primary Claude Desktop block (which was valid), but for strictness + regeneration hygiene I removed the partially-rendered block entirely and replaced it with a shell-comment snippet explaining the args-array translation.
- **Fix:** Replaced the invalid-JSON block with a `# equivalent args array...` shell comment immediately after the valid `uvx --prerelease=allow shopify-forecast-mcp@0.1.0rc1` shell block.
- **Files modified:** `docs/SETUP.md` (in-progress at the time — single commit).
- **Verification:** All 3 SETUP.md ```json blocks now parse cleanly; `test_claude_desktop_snippet_is_valid_json[docs/SETUP.md]` passes.
- **Committed in:** `9de0a4e`

**2. [Rule 3 - Blocking] Added a dedicated `uvx shopify-forecast-mcp` inline mention in README**

- **Found during:** Task 1, running `test_readme_shows_uvx_invocation` for the first time.
- **Issue:** The test asserts the literal string `uvx shopify-forecast-mcp` (with a space between `uvx` and the package name) appears in README.md. The JSON Claude Desktop snippet satisfies intent (`"command": "uvx", "args": ["shopify-forecast-mcp"]`) but not the literal substring check. Also, the plan action's draft README body had the snippet but no inline mention.
- **Fix:** Added a blockquote callout after the JSON snippet recommending `uvx shopify-forecast-mcp` as a terminal-first smoke test before wiring Claude Desktop. This provides genuine merchant value (pre-restart confidence check) AND satisfies the literal-string test.
- **Files modified:** `README.md`.
- **Verification:** `test_readme_shows_uvx_invocation` now passes.
- **Committed in:** `a1caea2`

---

**Total deviations:** 2 auto-fixed (both Rule 3 blocking — test / intent mismatches discovered during per-task verification). Both fixes improved the docs rather than adding scope.

## Issues Encountered

None — execution was clean. All 3 tasks passed their `<verify>` and `<acceptance_criteria>` checks first-run (after the 2 Rule 3 auto-fixes above, which were addressed before committing).

## Screenshot Capture Deferred Note

`docs/images/.gitkeep` creates the directory, but no screenshots are captured in this plan. Per plan `<output>` explicit guidance: *"screenshot capture deferred: Plan 4 creates `docs/images/.gitkeep` but does NOT capture screenshots — that's an explicit discretion item, and a clean Shopify admin screenshot set is best added during Plan 5 rc1 validation after the maintainer has the real workflow running."* Plan 5 (release cut) is the correct owner for real-portal screenshots.

## Release Pipeline Readiness

- **Plan 07-02 (publish workflow)** can now parse CHANGELOG.md `[0.1.0]` via `ffurrer2/extract-release-notes@v3`. Verified via awk extraction smoke test (27 bullet points under Added).
- **Plan 07-05 (release cut)** — README, SETUP, ARCHITECTURE, TOOLS, CHANGELOG are all stable, consistent, and cross-linked. rc1 walkthrough can proceed against these artifacts as-is; screenshot polish happens during rc1 validation.
- **No blockers** for Plan 07-02 or 07-03 from this plan (parallel in Wave 2 with no file overlap).

## Self-Check: PASSED

File existence:
- `README.md` (rewritten from placeholder) — FOUND
- `CHANGELOG.md` — FOUND
- `docs/SETUP.md` — FOUND
- `docs/ARCHITECTURE.md` — FOUND
- `docs/TOOLS.md` — FOUND
- `docs/images/.gitkeep` — FOUND

Commits exist:
- `a1caea2` — FOUND (docs(07-04): write README + CHANGELOG + docs/images placeholder)
- `9de0a4e` — FOUND (docs(07-04): write SETUP.md + ARCHITECTURE.md with 3 Mermaid diagrams)
- `b5842b7` — FOUND (docs(07-04): generate + enrich TOOLS.md (7-tool MCP reference))

All success criteria in plan met:
- [x] README.md rewritten per D-16 structure with all 12+ sections, alpha banner, 4 examples, uvx snippet, Claude Desktop JSON config.
- [x] CHANGELOG.md Keep-a-Changelog 1.1.0 format with [Unreleased] + [0.1.0] sections; [0.1.0] Added mentions all 7 tools + dual-backend + multi-store + covariates.
- [x] docs/SETUP.md covers all 4 scopes, both install paths, env var table, multi-store, CLI reference, troubleshooting; includes valid JSON Claude Desktop snippets for uvx + Docker + multi-store variants.
- [x] docs/ARCHITECTURE.md has 3 Mermaid diagrams rendering two-layer arch, data flow, backend selection; key decisions table with 14 entries referencing D-23 rationale.
- [x] docs/TOOLS.md has one section per tool (7 total) with Pydantic-generated Parameters table + Sample prompts + Example output; anchor-linked index at top.
- [x] docs/images/.gitkeep exists.
- [x] All tests in tests/test_docs_completeness.py, tests/test_changelog_structure.py, tests/test_claude_desktop_snippet.py pass with no skips (28 passed, 0 skipped).
- [x] No placeholder tokens (TODO, XXX, etc.) outside code blocks.

---
*Phase: 07-distribution-docs*
*Completed: 2026-04-19*
