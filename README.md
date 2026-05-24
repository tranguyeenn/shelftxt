# Shelftxt

Modular book ranking: manage a personal library, score read and to-read lists, and get a next-read suggestion. Supports flexible CSV ingestion with user-defined column mappings for batch analysis.

## Quick start

**Backend**

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.api:app --reload
```

**Frontend** (defaults to `http://127.0.0.1:8000` in dev)

```bash
cd frontend && npm install && npm run dev
```

Open `http://localhost:3000`.

**Tests**

```bash
./.venv/bin/python -m unittest discover -s tests -v
```

No sample library is bundled — `backend/data/processed/books.csv` is created empty on first use.

## Documentation

Technical docs live in **[`docs/`](docs/)**:

| Doc | Topic |
|-----|-------|
| [docs/README.md](docs/README.md) | Index |
| [docs/architecture.md](docs/architecture.md) | System design |
| [docs/data-model.md](docs/data-model.md) | CSV & canonical schemas |
| [docs/api.md](docs/api.md) | REST & proxy API |
| [docs/pipeline.md](docs/pipeline.md) | Flexible CSV pipeline |
| [docs/ranking.md](docs/ranking.md) | Scoring algorithms |
| [docs/frontend.md](docs/frontend.md) | Next.js UI |
| [docs/development.md](docs/development.md) | Setup, deploy, env |

## License

MIT — see [LICENSE](LICENSE).
