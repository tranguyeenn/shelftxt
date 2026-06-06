# Open source at shelftxt

Shelftxt is open source because reading tools should be inspectable, forkable, and affordable to run — not locked behind opaque algorithms or paid walls.

---

## Why open source

- **Transparency** — ranking logic, CSV persistence, and API behavior live in this repo; you can read how suggestions are built
- **Ownership** — your library is a file you can back up, diff, and migrate
- **Accessibility of cost** — designed for free-tier hosting (Vercel + Render) and standard Python/Node tooling
- **Solo sustainability** — one maintainer can keep the codebase honest without enterprise process overhead

MIT license: see [LICENSE](../../LICENSE).

---

## Mission: reading accessibility

Shelftxt exists to make **reading more accessible and less overwhelming**:

- Organize shelves without a subscription
- Reduce decision fatigue with ranked suggestions from *your* list
- Stay in control of your data (CSV export, no hidden training on your library)

Open source supports that mission: contributors and users can verify what the app does with their books.

---

## Documentation philosophy

Docs are written for **future maintainers and curious users**, not for compliance theater.

| Principle | Practice |
|-----------|----------|
| Truth over marketing | [architecture.md](../engineering/architecture.md) and [decisions.md](../product/decisions.md) record real trade-offs |
| Layered depth | Quick start in [README](../README.md); detail in `docs/` |
| Living history | [DEVLOG.md](../../DEVLOG.md) and [devlogs/](../history/devlogs) capture refactors and incidents |
| Small diffs | Doc updates ride along with code changes ([CONTRIBUTING.md](../../CONTRIBUTING.md)) |

Start at [docs/README.md](../README.md) for the full index.

---

## Devlogs

Engineering notes are public by design. When something non-obvious happens — a deploy fix, a backend refactor, a ranking quirk — it gets a dated entry under `docs/history/devlogs/` and a line in [DEVLOG.md](../../DEVLOG.md).

That is **engineering transparency**: not every project needs a blog, but this one documents how it evolved so you are not reverse-engineering git history alone.

---

## How to participate

- [CONTRIBUTING.md](../../CONTRIBUTING.md) — setup, conventions, review checklist
- [ROADMAP.md](../../ROADMAP.md) — realistic directions
- [CHANGELOG.md](../../CHANGELOG.md) — what changed between releases
- GitHub issue and PR templates under `.github/`

Security issues: [SECURITY.md](../../SECURITY.md) (private report, not public issues).

---

## Related

- [contributing.md](contributing.md) — workflow detail inside `docs/`
- [engineering/architecture.md](../engineering/architecture.md) — where code lives
