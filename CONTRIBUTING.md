# Contributing to ShelfTxt

Thanks for helping improve an open-source reading backend. ShelfTxt is maintained by one person — reviews may take time, especially for large or cross-cutting changes. Focused, well-tested PRs are appreciated.

---

## Quick links

| Topic | Document |
|-------|----------|
| **Setup and run locally** | [docs/development.md](docs/development.md) |
| **Day-to-day workflow and PR process** | [docs/development-workflow.md](docs/development-workflow.md) |
| **Where code lives** | [docs/architecture/system-overview.md](docs/architecture/system-overview.md) |
| **API reference** | [docs/api.md](docs/api.md) |
| **Extended conventions** | [docs/contributing.md](docs/contributing.md) |
| **Roadmap** | [ROADMAP.md](ROADMAP.md) |

---

## Ways to contribute

- Bug fixes
- Documentation improvements
- Tests
- Small feature additions
- Performance improvements
- Open issue resolution

Large architecture changes (storage migration, auth, breaking API changes) should start with an [issue discussion](.github/ISSUE_TEMPLATE/feature_request.md) before implementation.

---

## Getting started

### 1. Clone

```bash
git clone https://github.com/tranguyeenn/shelftxt.git
cd shelftxt
```

Fork on GitHub and clone your fork if you prefer working from your account.

### 2. Virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Use **Python 3.12+** (matches CI). Run commands from the **repo root**.

### 3. Verify tests pass

```bash
python -m unittest discover -s tests -v
```

### 4. Run the API

```bash
uvicorn backend.api:app --reload
```

- API: http://127.0.0.1:8000  
- Interactive docs: http://127.0.0.1:8000/docs  

Optional UI: `cd frontend && npm install && npm run dev` — see [docs/development.md](docs/development.md).

---

## Before you open a PR

1. **Run tests** (see above).
2. If you changed `frontend/`, run `npm run lint` and `npm run build` in `frontend/`.
3. **Update docs** when behavior, API paths, or deploy steps change — see [docs/development-workflow.md#documentation-updates](docs/development-workflow.md#documentation-updates).
4. Use the [pull request template](.github/PULL_REQUEST_TEMPLATE.md).
5. Ensure CI passes (Python tests + frontend TypeScript check).

Full checklist: [docs/development-workflow.md#local-verification-checklist](docs/development-workflow.md#local-verification-checklist).

---

## Coding expectations

- Match naming and import style in the file you edit (`from backend.X import Y` from repo root).
- Put business logic in `backend/services/`, not in route handlers.
- Use `apiUrl()` in the frontend — do not hardcode production API URLs.
- Do not commit `.venv/`, `.env*`, `frontend/.env.local`, or `backend/data/processed/books.csv`.
- Avoid new frameworks or abstraction layers without a concrete need.
- Prefer small, reviewable diffs over large rewrites.

Architecture map: [docs/architecture/system-overview.md](docs/architecture/system-overview.md).

---

## Issues and security

| Type | Template |
|------|----------|
| Bug | [.github/ISSUE_TEMPLATE/bug_report.md](.github/ISSUE_TEMPLATE/bug_report.md) |
| Feature | [.github/ISSUE_TEMPLATE/feature_request.md](.github/ISSUE_TEMPLATE/feature_request.md) |

Include reproduction steps, expected vs actual behavior, and environment (local vs production, Python version).

**Security:** Do not file public issues for vulnerabilities. See [SECURITY.md](SECURITY.md).

---

## Code of conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). Be respectful and constructive in issues and reviews.

---

## Related

- [docs/repository-audit.md](docs/repository-audit.md) — maintainer notes on repo health and gaps
- [docs/troubleshooting.md](docs/troubleshooting.md)
- [DEVLOG.md](DEVLOG.md)
