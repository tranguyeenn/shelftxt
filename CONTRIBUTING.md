# Contributing to shelftxt

Thanks for helping improve an open-source reading backend. Keep changes focused and documented.

---

## Ways to contribute

Contributions are welcome, including:

- Bug fixes
- Documentation improvements
- Backend refactors
- Tests
- Performance improvements
- Small feature additions
- Open issue resolution

Large architecture changes should begin with an issue discussion before implementation.

---

## Clone the repository

```bash
git clone https://github.com/tranguyeenn/shelftxt.git
cd shelftxt
```

Fork the repo on GitHub and clone your fork if you prefer working from a branch on your account.

---

## Virtual environment

From the repo root:

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

Use Python 3.12+ (see `requirements.txt`). Always activate the venv before installing or running commands.

---

## Install requirements

```bash
pip install -r requirements.txt
```

---

## Run FastAPI locally

```bash
uvicorn backend.api:app --reload
```

- API: http://127.0.0.1:8000  
- Interactive docs: http://127.0.0.1:8000/docs  

Legacy entrypoint: `uvicorn api:app --reload` (root shim).

Optional UI: `cd frontend && npm install && npm run dev` — see [docs/development.md](docs/development.md).

---

## Coding style expectations

- Match naming and import style in the file you edit (`from backend.X import Y` from repo root).
- Put business logic in `backend/services/`, not in route handlers.
- Do not commit `.venv/`, `.env*`, `frontend/.env.local`, or `backend/data/processed/books.csv`.
- Avoid new frameworks or extra abstraction layers without a concrete need.
- Update [docs/api.md](docs/api.md) when public paths or payloads change.
- Prefer small, reviewable diffs over large rewrites.

Architecture map: [docs/architecture/system-overview.md](docs/architecture/system-overview.md).

---

## Pull request guidelines

1. Branch from `main` (or your fork’s default branch).
2. Run tests before opening a PR:

   ```bash
   python -m unittest discover -s tests -v
   ```

3. Use the [pull request template](.github/PULL_REQUEST_TEMPLATE.md) checklist.
4. Describe what changed and why; link related issues when applicable.
5. Update docs if behavior, deploy steps, or layout changed.

This is a solo-maintained project — review may take time. Large changes benefit from a prior [feature request](.github/ISSUE_TEMPLATE/feature_request.md) or issue discussion.

---

## Issue reporting

| Type | Template |
|------|----------|
| Bug | [.github/ISSUE_TEMPLATE/bug_report.md](.github/ISSUE_TEMPLATE/bug_report.md) |
| Feature | [.github/ISSUE_TEMPLATE/feature_request.md](.github/ISSUE_TEMPLATE/feature_request.md) |

Include reproduction steps, expected vs actual behavior, and environment (local vs production, Python version).

**Security:** Do not file public issues for vulnerabilities. See [SECURITY.md](SECURITY.md).

---

## Related

- [ROADMAP.md](ROADMAP.md)
- [docs/contributing.md](docs/contributing.md) — extra workflow and doc-update table
- [docs/troubleshooting.md](docs/troubleshooting.md)
