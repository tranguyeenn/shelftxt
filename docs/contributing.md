# Contributing

How to work on shelftxt — setup, workflow, and what we expect in changes.

**Start here:** [CONTRIBUTING.md](../CONTRIBUTING.md) (clone, setup, PR and issue guidelines).

**Day-to-day workflow:** [development-workflow.md](development-workflow.md) (branching, local checks, CI, doc updates).

For **where code lives**, see [architecture/system-overview.md](architecture/system-overview.md). For **why** structural choices were made, see [decisions.md](decisions.md).

---

## Before you start

1. Complete local setup: [development.md](development.md)
2. Skim the folder map: [architecture/system-overview.md](architecture/system-overview.md)
3. If you are changing behavior users see, check [api.md](api.md) for public paths

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
- [ ] Public API paths unchanged (`/books`, `/recommend`, …) **or** [api.md](api.md) updated
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
- Expand scope “while you’re here” unless you log it in a [devlog](devlogs/)

Full layer rules: [architecture/system-overview.md#backend-layer-rules](architecture/system-overview.md#backend-layer-rules).

---

## Documentation

| If you changed… | Update… |
|-----------------|---------|
| API request/response or paths | [api.md](api.md), [system-design/api-design.md](system-design/api-design.md) |
| Deploy / env vars | [deployment.md](deployment.md) |
| Folder responsibilities | [architecture/system-overview.md](architecture/system-overview.md) |
| Non-obvious trade-off | [decisions.md](decisions.md) or a new [devlog](devlogs/) entry |
| Refactor or incident worth remembering | [DEVLOG.md](../DEVLOG.md) + `docs/devlogs/YYYY-MM-DD-*.md` |
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
| [repository-audit.md](repository-audit.md) | Known gaps and improvement backlog |
| [architecture/system-overview.md](architecture/system-overview.md) | Where to put code |
| [architecture.md](architecture.md) | Diagrams, data paths, production topology |
| [decisions.md](decisions.md) | ADRs |
| [troubleshooting.md](troubleshooting.md) | Tests failing, deploy errors |
| [DEVLOG.md](../DEVLOG.md) | Engineering timeline |
