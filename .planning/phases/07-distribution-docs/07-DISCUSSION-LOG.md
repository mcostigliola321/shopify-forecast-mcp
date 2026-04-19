# Phase 7: Distribution & Docs - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-19
**Phase:** 07-distribution-docs
**Areas discussed:** PyPI release flow, Docker strategy, Docs scope & style, v0.1.0 release positioning

---

## Gray Area Selection

| Option | Description | Selected |
|--------|-------------|----------|
| PyPI release flow | Trigger, staging, Python matrix, artifact scope | ✓ |
| Docker strategy | Base image Python conflict, platforms, bundled-model strategy, entrypoint/credentials | ✓ |
| Docs scope & style | Client coverage, diagrams, TOOLS.md depth, voice | ✓ |
| v0.1.0 release positioning | Classifier, RC dry-run, changelog, announce scope | ✓ |

**User's choice:** All four.

---

## PyPI Release Flow

### Q1. Publish trigger — when should the publish workflow run?

| Option | Description | Selected |
|--------|-------------|----------|
| On version tag (v*) | Push tag like v0.1.0 → CI tests → build → publish via OIDC. Simple, matches ROADMAP plan 4. | ✓ |
| On GitHub Release creation | Draft a Release in GitHub UI → workflow fires on publish event. | |
| Tag + manual dispatch backup | Tag-triggered primary, workflow_dispatch secondary. | |

**User's choice:** On version tag (v*) — recommended.

### Q2. Staging before PyPI — should we ship to TestPyPI first?

| Option | Description | Selected |
|--------|-------------|----------|
| Direct to PyPI on tag | Skip TestPyPI. Single maintainer, alpha, CI + uv build already covers pre-tag testing. | ✓ |
| TestPyPI on -rc* tags, PyPI on clean tags | Two Trusted Publisher registrations, pre-release staging. | |
| TestPyPI always, then PyPI on approval | Manual environment-protected approval gate. Safest, slowest. | |

**User's choice:** Direct to PyPI on tag — recommended.

### Q3. Python version matrix for the publish workflow's test job

| Option | Description | Selected |
|--------|-------------|----------|
| Python 3.11 only | Matches pyproject pin (>=3.11,<3.12). Existing CI already covers 3.11 on Ubuntu + macOS. | ✓ |
| 3.11 + 3.12 (widen pyproject too) | Open to 3.12, matches ROADMAP's python:3.12-slim Docker intent. More surface. | |
| 3.11 on Ubuntu + macOS, gate on existing CI job | Don't duplicate, publish job depends on smoke job being green. | |

**User's choice:** Python 3.11 only — recommended.

### Q4. Publish workflow artifact scope

| Option | Description | Selected |
|--------|-------------|----------|
| PyPI + GitHub Release w/ built wheels attached | gh release create, attach dist/*, populate notes from CHANGELOG. | ✓ |
| PyPI only | Minimal. Tag exists in git, package on PyPI, nothing else. | |
| PyPI + GitHub Release notes only (no artifacts) | Release page exists, but wheels only on PyPI. | |

**User's choice:** PyPI + GitHub Release w/ built wheels attached — recommended.

---

## Docker Strategy

### Q1. Resolving the Python version conflict (ROADMAP 3.12-slim vs pyproject <3.12)

| Option | Description | Selected |
|--------|-------------|----------|
| Keep 3.11 everywhere: Docker base = python:3.11-slim | Consistent with pyproject, tested CI matrix, TimesFM known-good. | ✓ |
| Widen to 3.12 | Update pyproject to >=3.11,<3.13, add 3.12 to CI, Docker uses 3.12-slim. | |
| Docker 3.11, pyproject untouched, revisit in v0.2 | Same as option 1, explicit defer note. | |

**User's choice:** Keep 3.11 everywhere — recommended.
**Notes:** Code reality wins over aspirational ROADMAP wording.

### Q2. Docker platforms

| Option | Description | Selected |
|--------|-------------|----------|
| linux/amd64 + linux/arm64 | Multi-arch via buildx. Native Apple Silicon support. Slower builds. | ✓ |
| linux/amd64 only | Faster CI, simpler. arm64 users pay emulation tax. | |
| linux/amd64 now, arm64 follow-up | Ship amd64 for v0.1.0, arm64 in point release. | |

**User's choice:** linux/amd64 + linux/arm64 — recommended.

### Q3. Bundled image model strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Build-stage RUN: from_pretrained into /opt/hf-cache, COPY into final | Matches ROADMAP plan 2 literally. Deterministic, no runtime download. | ✓ |
| Bake via huggingface-cli download in build stage | Avoids torch/timesfm import at build time. Different layout than runtime. | |
| Side-load weights at runtime via volume mount | Keeps image small but fails "starts without internet" success criterion. | |

**User's choice:** Build-stage from_pretrained — recommended.

### Q4. Container entrypoint + credential delivery

| Option | Description | Selected |
|--------|-------------|----------|
| Env-var token only; entrypoint = shopify-forecast-mcp | DirectBackend path via env vars. OAuth doesn't work in containers anyway. | |
| Shopify CLI inside container + mounted auth dir | Bake CLI, mount ~/.config/shopify. Fragile, ~100MB bloat. | |
| Flexible entrypoint script that dispatches to MCP server or CLI | Custom entrypoint.sh reads first arg. Nicer UX, more moving parts. | ✓ |

**User's choice:** Flexible entrypoint script.
**Notes:** Enables one-shot CLI runs like `docker run ... revenue --horizon 30` without losing MCP server as default.

---

## Docs Scope & Style

### Q1. MCP client coverage in README + SETUP.md

| Option | Description | Selected |
|--------|-------------|----------|
| Claude Desktop + Claude Code + generic snippet | Full walkthroughs for two biggest, generic spec for Cursor/custom. | ✓ |
| Claude Desktop only, others as footnote | One hero walkthrough, rest as links. | |
| Claude Desktop + Claude Code + Cursor + Shopify Sidekick teaser | Four clients + forward-looking teaser. More surface. | |

**User's choice:** Claude Desktop + Claude Code + generic — recommended.

### Q2. Architecture diagrams

| Option | Description | Selected |
|--------|-------------|----------|
| Mermaid (rendered by GitHub) | Version-controlled, diff-able, no external tools. | ✓ |
| ASCII art diagrams | Always renders, less readable for complex flows. | |
| Prose only | No diagrams, structured headings and bullets. | |

**User's choice:** Mermaid — recommended.

### Q3. TOOLS.md depth

| Option | Description | Selected |
|--------|-------------|----------|
| Per-tool section: schema + 2 prompts + 1 rendered markdown output | Matches R11.3. ~150 lines per tool. | ✓ |
| Summary table + deep-link to source | Lighter. Weaker R11.3 match. | |
| Per-tool section but schemas only | Skip rendered outputs. Schemas drift slower. | |

**User's choice:** Full per-tool sections — recommended.

### Q4. Docs voice

| Option | Description | Selected |
|--------|-------------|----------|
| Merchant-operator friendly, with 'for developers' call-outs | Primary voice is store owner, dev detail in call-outs. | ✓ |
| Developer reference — terse, spec-like | Assumes Python+uv+OIDC fluency. Narrower audience. | |
| Two-track: README merchant, docs/* dev-focused | Split personality. Consistent if done carefully. | |

**User's choice:** Merchant-operator friendly — recommended.

---

## v0.1.0 Release Positioning

### Q1. Release classification

| Option | Description | Selected |
|--------|-------------|----------|
| Alpha — keep classifier 'Development Status :: 3 - Alpha' | Honest for zero-external-user launch. Current classifier. | ✓ |
| Beta — update to 'Development Status :: 4 - Beta' | Stronger invitation, expects bug reports. | |
| Production/Stable — 'Development Status :: 5 - Production/Stable' | Implies API stability guarantees not yet committed. | |

**User's choice:** Alpha — recommended.

### Q2. Pre-release candidate before v0.1.0?

| Option | Description | Selected |
|--------|-------------|----------|
| Cut v0.1.0-rc1 first to exercise CI → PyPI → GHCR | De-risks launch. Only cost is one extra tag + PyPI pre-release version. | ✓ |
| Straight to v0.1.0 | Faster, but OIDC misconfig or GHCR scope issue burns the canonical tag. | |
| Local dry-run only: act + buildx, then straight to v0.1.0 | No PyPI junk versions. Won't catch real Trusted Publisher/GHCR auth issues. | |

**User's choice:** Cut v0.1.0-rc1 first — recommended.

### Q3. Changelog approach

| Option | Description | Selected |
|--------|-------------|----------|
| CHANGELOG.md (Keep a Changelog) + GitHub Release notes mirror | Single source of truth, standard format, scannable. | ✓ |
| GitHub Release notes only | Lighter. Harder to diff history without clicking through releases. | |
| CHANGELOG.md + auto-generated from commits | Zero manual maintenance, but commit hygiene across 26 phase commits varies. | |

**User's choice:** CHANGELOG.md + GH Release notes mirror — recommended.

### Q4. Launch announcement scope

| Option | Description | Selected |
|--------|-------------|----------|
| GitHub Release notes + short README banner + pinned repo issue | Announce where MCP-interested devs look. Minimal effort, high-signal audience. | ✓ |
| Add Shopify community + MCP directory listings | Wider reach, more work, requires tracking response. | |
| Full launch: above + X/LinkedIn/HN + dev.to writeup | Product launch treatment. Biggest reach, biggest time sink. | |
| No announce — organic adoption | Ship quietly, iterate to v0.2. Weakest feedback loop. | |

**User's choice:** GitHub Release + README banner + pinned issue — recommended.

---

## Claude's Discretion

The user deferred the following to Claude (captured in CONTEXT.md `<decisions>` section under "Claude's Discretion"):

- Exact Mermaid diagram syntax and layout
- Shell syntax details in `/app/entrypoint.sh`
- Precise wording of `CHANGELOG.md [0.1.0] Added` entries
- Screenshot tooling and image storage location in `docs/`
- Whether to add `publiccode.yml` or `citation.cff`
- Publish workflow runner OS
- Whether to include a Docker `HEALTHCHECK` directive (likely no, since MCP is stdio)
- Anchor slug conventions in TOOLS.md

---

## Deferred Ideas

Captured in CONTEXT.md `<deferred>` section:

- Shopify Sidekick App Extension (future phase)
- Per-client walkthroughs for Cursor / custom agents (consolidated to generic spec for v0.1.0)
- Landing site / GitHub Pages (repo README is the landing page)
- SBOM / sigstore / attestations supply-chain hardening (post-v0.1.0)
- awesome-mcp / Shopify community directory submissions (v0.2 announce plan)
- Widening `pyproject.toml` to Python 3.12 (revisit in v0.2)
- `workflow_dispatch` manual publish trigger (add in v0.1.1 if recovery needed)
- Docker `HEALTHCHECK` (revisit if we ship SSE/streamable-http image tags)
