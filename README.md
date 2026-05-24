# Shelftxt

Modular book ranking: manage a personal library, score read and to-read lists, and get a next-read suggestion. Supports flexible CSV ingestion with user-defined column mappings for batch analysis.

**Live:** [shelftxt.vercel.app](https://shelftxt.vercel.app) · API [shelftxt.onrender.com/docs](https://shelftxt.onrender.com/docs)

## Quick start

**Backend**

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.api:app --reload
```

**Frontend**

```bash
cd frontend && npm install && npm run dev
```

Open http://localhost:3000. See [docs/development.md](docs/development.md) for remote-API-only dev (no local uvicorn).

**Tests**

```bash
./.venv/bin/python -m unittest discover -s tests -v
```

No sample library is bundled — `backend/data/processed/books.csv` is created empty on first use.

## Documentation

| Doc | Topic |
|-----|-------|
| [docs/README.md](docs/README.md) | **Doc index** — start here |
| [docs/architecture.md](docs/architecture.md) | System design, layers, topology |
| [docs/deployment.md](docs/deployment.md) | Render + Vercel runbook |
| [docs/decisions.md](docs/decisions.md) | Architecture decisions (ADRs) |
| [docs/contributing.md](docs/contributing.md) | Conventions & PR checklist |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Common errors |
| [docs/development.md](docs/development.md) | Local setup |
| [docs/api.md](docs/api.md) | REST reference |
| [docs/data-model.md](docs/data-model.md) | CSV schemas |
| [docs/ranking.md](docs/ranking.md) | Scoring algorithms |
| [docs/pipeline.md](docs/pipeline.md) | Batch CSV pipeline |
| [docs/frontend.md](docs/frontend.md) | Next.js UI |

## License

MIT — see [LICENSE](LICENSE).
