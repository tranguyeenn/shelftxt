# Changelog

All notable changes to ShelfTxt are documented here.

This file tracks architectural changes, feature additions, refactors, and decisions that meaningfully affect development.

---

## [Unreleased]

### Added

- Open-source maintenance files:
  - `CONTRIBUTING.md`
  - `ROADMAP.md`
  - `SECURITY.md`
  - GitHub issue + PR templates
  - GitHub Actions test workflow

- Engineering documentation:
  - `docs/history/devlogs/`
  - architecture notes
  - deployment notes
  - troubleshooting docs

- Repository structure intended to support long-term maintenance and public contributions

### Changed

- Refactored backend structure toward:

```txt
routes → services → repositories → preprocessing → ranking
```

to reduce API complexity and improve maintainability.

- Expanded documentation to include:
  - development workflow
  - deployment
  - architecture decisions
  - troubleshooting
  - engineering logs

### Motivation

These changes were made to:

- improve maintainability
- reduce backend complexity
- document architectural decisions
- support future contributors (including future-me)

---

## Future releases

Versioned milestones may be added as ShelfTxt evolves.

Early development changes are documented primarily through:

- [DEVLOG.md](DEVLOG.md)
- [docs/history/devlogs/](docs/history/devlogs/)
