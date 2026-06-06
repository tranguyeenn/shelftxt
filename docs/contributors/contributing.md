# Contributing

How to work on shelftxt — setup, workflow, and what we expect in changes.

**Start here:** [CONTRIBUTING.md](../../CONTRIBUTING.md) (clone, setup, PR and issue guidelines).

**Day-to-day workflow:** [development-workflow.md](development-workflow.md) (branching, local checks, CI, doc updates).

For **where code lives**, see [engineering/architecture.md](../engineering/architecture.md). For **why** structural choices were made, see [decisions.md](../product/decisions.md).

---

## Before you start

1. Complete local setup: [development.md](development.md)
2. Skim the folder map: [engineering/architecture.md](../engineering/architecture.md)
3. If you are changing behavior users see, check [api.md](../engineering/api.md) for public paths

This is a solo-friendly repo — there is no heavy review process. These guidelines still help future-you and anyone reading the history.

---

## Workflow

1. **Branch** from `main` (or work directly on `main` if you are the only contributor).
2. **Keep diffs focused** — one feature or refactor per change set when possible.
3. **Run tests** before pushing:

   ```bash
   ./.venv/bin/python -m unittest discover -s tests -v
   ```

4. **Update docs** when you change API paths, deploy steps, or project layout (see [Documentation](#documentation) below).
5. **Push** and deploy Render/Vercel if the change affects production.

---

## Pull request checklist

Use this even for self-review before merge:

- [ ] `./.venv/bin/python -m unittest discover -s tests -v` passes
- [ ] No secrets, API keys, or `backend/data/processed/books.csv` in the diff
- [ ] Public API paths unchanged (`/books`, `/recommend`, …) **or** [api.md](../engineering/api.md) updated
- [ ] Relevant docs updated (see table below)
- [ ] Scope is minimal — no drive-by refactors unrelated to the task

---

## Code conventions (short)

**Do**

- Match naming and import style in the file you are editing
- Put new business logic in `backend/services/`, not in route handlers
- Use `from backend.X import Y` (repo root is on the Python path)
- Use `apiUrl()` in the frontend — do not hardcode production API URLs in components

**Don't**

- Commit `.env.local`, venvs, or personal CSV libraries
- Add frameworks (DI containers, extra abstractions) without a concrete need
- Expand scope “while you’re here” unless you log it in a [devlog](../history/devlogs)

Full layer rules: [engineering/architecture.md#backend-layer-rules](../engineering/architecture.md#backend-layer-rules).

---

## Documentation

| If you changed… | Update… |
|-----------------|---------|
| API request/response or paths | [api.md](../engineering/api.md) |
| Deploy / env vars | [deployment.md](../engineering/deployment.md) |
| Folder responsibilities | [engineering/architecture.md](../engineering/architecture.md) |
| Non-obvious trade-off | [decisions.md](../product/decisions.md) or a new [devlog](../history/devlogs) entry |
| Refactor or incident worth remembering | [DEVLOG.md](../../DEVLOG.md) + `docs/history/devlogs/YYYY-MM-DD-*.md` |
| “It broke and we fixed it” | [troubleshooting.md](troubleshooting.md) |

---

## Commit messages

Prefer imperative, scoped summaries:

```txt
Extract delete book into services/books.py
Fix Vercel production fetch via apiUrl helper
Document Render monorepo root directory
```

---

## Related

| Doc | Use when |
|-----|----------|
| [development.md](development.md) | Install, run locally, CLI |
| [development-workflow.md](development-workflow.md) | End-to-end contributor workflow |
| [repository-audit.md](../history/audits/repository-audit.md) | Known gaps and improvement backlog |
| [engineering/architecture.md](../engineering/architecture.md) | System architecture, folder map, diagrams |
| [decisions.md](../product/decisions.md) | ADRs |
| [troubleshooting.md](troubleshooting.md) | Tests failing, deploy errors |
| [DEVLOG.md](../../DEVLOG.md) | Engineering timeline |
