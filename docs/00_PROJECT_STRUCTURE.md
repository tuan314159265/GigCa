# Project structure

```text
GigCa/
├── api/                 # Role Backend: API and integration layer
│   ├── src/
│   └── tests/
├── config/              # Versioned, non-secret model/product configuration
├── contracts/           # Shared API examples and JSON Schemas
├── data/
│   ├── raw/              # Local-only source files; ignored by Git
│   ├── processed/        # Generated/local processed data; ignored by Git
│   ├── fixtures/         # Small, licensed or synthetic, clearly labeled fixtures
│   └── samples/          # Small fetched snapshots with provenance and descriptions
├── docs/                # Architecture, API, schema, and user guide
├── engine/              # Role Decision model: candidate generation and scoring
│   ├── src/
│   └── tests/
├── infra/               # Deployment/local orchestration notes and manifests
├── scripts/             # Data ingestion and reproducible utility commands
└── web/                 # Role Frontend: map and recommendation UI
    ├── public/
    └── src/
```

Role Data primarily owns `data/` and `scripts/`. Keep source metadata with each dataset; do not commit raw feeds by default. `data/fixtures/` is the only shared data directory and must contain small, safe, provenance-labeled fixtures.

Backend is planned with FastAPI/Pydantic; frontend with React, TypeScript, Vite, Leaflet and GeoJSON; the engine is planned in Python. This is the intended direction from the current plan, not a declaration that scaffolding or dependency versions have been selected.
