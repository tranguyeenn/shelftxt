# Repository audit

Snapshot of ShelfTxt repository health — documentation, CI, onboarding, and structural gaps. Intended for maintainers planning improvements. Last reviewed: **2026-05-30**.

---

## Executive summary

ShelfTxt has **strong technical documentation** (system design, ADRs, devlogs) and a **working Python test suite with CI**. Onboarding is split across several docs with some overlap. **Frontend type-checking is now in CI**; Python linting/formatting is not. The largest structural debt is **shared CSV storage** and **legacy files** (`api_draft.py`) documented elsewhere in the roadmap.

This audit recommends small, incremental improvements appropriate for a solo-maintained open-source project — not enterprise tooling overhead.

---

## Repository layout

| Area | Status | Notes |
|------|--------|-------|
| `backend/` | Good | Clear layers: routes → services → repository |
| `frontend/` | Good | Vite + React; `npm run lint` = TypeScript check |
| `tests/` | Good | 4 test modules; API tests mock at boundaries |
| `docs/` | Strong | System design, user research, devlogs |
| `cli/` | Minimal | Single helper script; documented in development.md |
| `.github/` | Adequate | Issue/PR templates; CI workflows |

### Legacy / cleanup candidates

| Item | Issue | Recommendation |
|------|-------|----------------|
| `backend/api_draft.py` | Monolithic legacy API; not loaded in production | Delete when no references remain ([roadmap](../../product/roadmap.md)) |
| `api.py` (root) | Shim for `uvicorn api:app` | Keep until deploy docs fully standardize on `backend.api:app` |
| Duplicate contributing docs | `CONTRIBUTING.md` + `docs/contributors/contributing.md` | CONTRIBUTING.md = GitHub entry; docs/contributors/contributing.md = extended reference |
| Python version docs | CONTRIBUTING says 3.12+; development.md says 3.14+ | Align docs to CI (3.12) unless 3.14 is intentional |

---

## Documentation

### What exists (strengths)

- README with architecture summary, setup, and API table
- [docs/README.md](../../README.md) index with clear "start here" paths
- System design folder (10+ focused documents)
- ADRs in [decisions.md](../../product/decisions.md)
- Engineering devlogs ([DEVLOG.md](../../../DEVLOG.md))
- Deployment and troubleshooting runbooks
- User research section (unusual and valuable for OSS)
- SECURITY.md, CODE_OF_CONDUCT.md, CHANGELOG.md, ROADMAP.md

### Gaps and improvements

| Gap | Severity | Suggestion |
|-----|----------|------------|
| No single "first PR" walkthrough | Medium | **Addressed:** [development-workflow.md](../../contributors/development-workflow.md) |
| Python version inconsistency | Low | Pick one minimum (3.12 to match CI); update development.md |
| No `docs/testing.md` | Low | Optional: document mock patterns from test_api.py |
| No architecture diagram in README beyond ASCII | Low | Acceptable for project size |
| Frontend testing docs absent | Low | Document that frontend has no automated tests yet |
| `requirements-dev.txt` underdocumented | Low | Note pytest is optional; CI uses unittest |
| No CODEOWNERS | Low | Optional for solo maintainer |
| No `good first issue` labels documented | Low | Tag beginner-friendly issues in GitHub |

---

## Continuous integration

### Before this audit

| Check | Status |
|-------|--------|
| Python unit tests on push/PR | Yes — `.github/workflows/tests.yml` |
| Frontend TypeScript lint | No |
| Python lint (ruff, pyright, mypy) | No tooling in repo |
| Frontend unit/E2E tests | No |
| Dependabot / Renovate | No |
| Deploy preview | Relies on Vercel/Render defaults |

### After recommended changes

| Check | Status |
|-------|--------|
| Python unit tests | Unchanged — tests.yml |
| Frontend CI (lint + build) | **Added** — `.github/workflows/frontend-ci.yml` |

### Future CI (suggested issues, not required now)

| Enhancement | When to add |
|-------------|-------------|
| `ruff` for Python lint + format | When contributor count grows or style drift appears |
| `pyright` or `mypy` | When types expand beyond current annotations |
| pytest in CI (alongside unittest) | If tests migrate to pytest fixtures |
| Frontend Vitest | When UI logic complexity justifies it |
| Dependabot for npm/pip | When dependency update volume increases |
| CI matrix (Python 3.12, 3.13) | Before declaring broader Python support |

---

## Onboarding experience

### Current path for new contributors

1. README → CONTRIBUTING.md
2. CONTRIBUTING.md → development.md (setup)
3. docs/contributors/contributing.md (conventions)
4. engineering/architecture.md (where to put code)

### Improvements made

- [development-workflow.md](../../contributors/development-workflow.md) — end-to-end workflow in one place
- CONTRIBUTING.md updated — clearer navigation and CI expectations

### Remaining friction

| Friction | Mitigation |
|----------|------------|
| Many doc entry points | Use docs/README.md "Start here" table as canonical router |
| No devcontainer / Docker | Optional future issue; venv is sufficient for now |
| Shared CSV on Render demo | Documented demo mode; Postgres migration is the real fix |
| Slow PR review (solo maintainer) | Stated in CONTRIBUTING.md |

---

## Testing coverage

| Area | Coverage | Notes |
|------|----------|-------|
| API routes | Partial | test_api.py mocks services/repo |
| Ranking | Good | test_score.py |
| Recommendation builder | Good | test_recommendation_builder.py |
| Ingest pipeline | Partial | Happy path + schema rejection |
| Frontend | None | Manual smoke only |
| CLI | None | Low priority |

Suggested test additions (future issues):

- CSV validation edge cases (empty file, encoding errors)
- Exception handling paths in services
- Pagination boundary cases beyond existing API tests

---

## Security and hygiene

| Item | Status |
|------|--------|
| `.gitignore` covers venv, .env, books.csv | Yes |
| SECURITY.md | Yes |
| Secrets in CI | None required for current workflows |
| CORS configured explicitly | Yes — backend/api.py |
| Demo read-only guard | Yes — demo_mode middleware |

---

## Open-source governance

| Item | Present |
|------|---------|
| LICENSE (MIT) | Yes |
| CODE_OF_CONDUCT.md | Yes |
| CONTRIBUTING.md | Yes |
| Issue templates | Yes |
| PR template | Yes |
| FUNDING.yml | Yes |
| CHANGELOG.md | Yes |

Missing (optional for small OSS):

- GOVERNANCE.md (not needed at current scale)
- `.github/SUPPORT.md`
- Release automation / tagged releases workflow

---

## Priority backlog

Ordered for a small open-source project:

1. **Delete `api_draft.py`** when confirmed unused
2. **Align Python version** in all docs to match CI (3.12+)
3. **Add `good first issue` labels** to 2–3 starter tasks
4. **Expand ingest/validation tests** for error paths
5. **Add ruff** when Python contributor volume increases
6. **Postgres migration planning** — tracked in ROADMAP.md (largest architectural item)

---

## Related

- [development-workflow.md](../../contributors/development-workflow.md)
- [CONTRIBUTING.md](../../../CONTRIBUTING.md)
- [ROADMAP.md](../../../ROADMAP.md)
- [product/roadmap.md](../../product/roadmap.md)
