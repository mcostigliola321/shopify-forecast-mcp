---
phase: 07-distribution-docs
status: passed
verified: 2026-04-20
method: live-release
evidence: production artifacts on PyPI + GHCR + GitHub Releases
---

# Phase 07: Distribution & Docs — VERIFICATION

## Phase goal

> One-command install for merchants via `uvx`, Docker images on GHCR (lazy + bundled), and documentation that gets a new user clone-to-running in under 5 minutes.

**Verified: passed.** Verification is not desk-based this time — the actual live release is the evidence.

## Requirements coverage

| ID | Requirement | Evidence | Status |
|----|-------------|----------|--------|
| R11.1 | README.md merchant-first landing page | https://github.com/mcostigliola321/shopify-forecast-mcp (179 lines, 4 JSON blocks parse) | ✅ |
| R11.2 | docs/SETUP.md end-to-end install guide | 321 lines, covers uvx + docker + Claude Desktop snippets, JSON valid | ✅ |
| R11.3 | docs/ARCHITECTURE.md with Mermaid diagrams | 153 lines, 3 diagrams (dual-backend, data flow, MCP lifecycle) | ✅ |
| R11.4 | docs/TOOLS.md auto-generated from Pydantic schemas | 311 lines, 7 tool sections generated via `scripts/gen_tools_doc.py` | ✅ |
| R11.5 | CHANGELOG.md [0.1.0] seeded | 51 lines, Keep-a-Changelog format, [0.1.0] - 2026-04-19 | ✅ |
| R12.1 | `uvx` install path | `uvx --from shopify-forecast-mcp==0.1.0 shopify-forecast --help` → 30.1s cold, prints 6 subcommands | ✅ |
| R12.2 | Docker image on GHCR multi-arch | `ghcr.io/mcostigliola321/shopify-forecast-mcp:latest` — 4 manifests (amd64+arm64 + 2 OCI attestations) | ✅ |
| R12.3 | `:bundled` variant offline-capable | `:bundled` tag pushed; TimesFM weights baked into `/opt/hf-cache` at build time (model-downloader stage) | ✅ |
| R12.4 | PyPI Trusted Publisher (no static tokens) | Upload succeeded via OIDC exchange, no secrets in publish.yml | ✅ |
| R12.5 | Maintainer runbook | `docs/RELEASE.md` (228 lines) reflects final fixed pipeline | ✅ |

## Must-haves by plan

### 07-01 (dependency swap + Wave 0 infrastructure)
- ✅ Wheel METADATA: `Requires-Dist: timecopilot-timesfm<0.3,>=0.2` (no `git+https`)
- ✅ `uv build` + `twine check` PASSED on wheel + sdist
- ✅ Full test suite: 354 passed, 12 deselected (slow/integration)
- ✅ 5 Wave 0 test files with 48 `def test_*` functions
- ✅ `scripts/gen_tools_doc.py` renders 7 tool sections via Pydantic v2 introspection

### 07-02 (publish workflow)
- ✅ `.github/workflows/publish.yml` present (227 lines, 5 jobs)
- ✅ `id-token: write` scoped to publish-pypi only
- ✅ `packages: write` scoped to publish-docker only
- ✅ Multi-arch matrix (linux/amd64, linux/arm64)
- ✅ rc-tag discrimination via 4 `enable=` conditional tag rules
- ✅ wait-for-ci blocks on ci.yml same-SHA pass (D-03)

### 07-03 (Docker images)
- ✅ Dockerfile 4-stage, 2 targets (runtime-lazy, runtime-bundled)
- ✅ `docker-entrypoint.sh` verb dispatcher
- ✅ `.dockerignore` filters secrets + build context
- ✅ `target: runtime-${{ matrix.variant }}` contract match with publish.yml
- ✅ STRIDE threats T-07-05, T-07-11, T-07-12, T-07-13, T-07-15 mitigated

### 07-04 (documentation suite)
- ✅ 28/28 docs tests pass (test_docs_completeness + test_changelog_structure + test_claude_desktop_snippet)
- ✅ 3 Mermaid diagrams in ARCHITECTURE.md
- ✅ 4 JSON blocks in SETUP.md parse cleanly
- ✅ 7 tool sections in TOOLS.md

### 07-05 (release procedure + tag cut)
- ✅ `docs/RELEASE.md` runbook written
- ✅ PyPI Trusted Publisher registered and exercised
- ✅ `v0.1.0-rc1` 4 D-20 legs verified (PyPI + GHCR + Release + stopwatch)
- ✅ `v0.1.0` stable shipped with mutable-tag advancement

## Live verification evidence

```text
$ curl -sS https://pypi.org/pypi/shopify-forecast-mcp/0.1.0/json | python3 -c "..."
  Version: 0.1.0
  Files:   2 (wheel + sdist)

$ gh release view v0.1.0 --json isPrerelease
  {"isPrerelease":false}

$ docker manifest inspect ghcr.io/mcostigliola321/shopify-forecast-mcp:latest
  manifests: [amd64, arm64, unknown (OCI attestation), unknown (OCI attestation)]

$ time uvx --from shopify-forecast-mcp==0.1.0 shopify-forecast --help
  Usage: shopify-forecast [-h] {revenue,demand,auth,promo,compare,scenarios} ...
  5.07s user 4.43s system 31% cpu 30.131 total
```

## Regression check

Ran full non-slow test suite after phase completion:
- `354 passed, 12 deselected (slow/integration), 2 warnings in 2.71s`
- 2 warnings are pre-existing asyncio coroutine warnings in `test_cli.py` and `test_cli_auth.py` (not introduced by Phase 7).

No cross-phase regressions detected.

## Deviations from plan (accepted)

1. **Owner mismatch:** Plan assumed GitHub owner `omnialta`; actual is `mcostigliola321`. 84 references swept across 22 files. Email `mark@omnialta.com` preserved (real domain).
2. **Two workflow bugs surfaced by real CI:**
   - Dockerfile missing `COPY README.md LICENSE` before `--no-editable` sync (hatchling requires files referenced in pyproject.toml `readme` / `license-files`). Fixed in commit `4f32276`.
   - PyPI upload not idempotent across retagged SHAs (sdist hash drifts). Fixed with pre-check step that short-circuits when version exists on PyPI (commit `d179099`).
3. **Three rc1 iterations** before final success. All bugs fixed in-flight; `docs/RELEASE.md` reflects the post-fix pipeline so future maintainers don't re-hit them.

## Conclusion

Phase 07 goal achieved. v0.1.0 is live and merchant-installable via three distribution channels. Ready for milestone completion.
