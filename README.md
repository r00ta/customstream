# Simplestream Manager

A FastAPI-based service and Vanilla Framework front-end that helps MAAS administrators mirror
upstream simplestreams and publish custom OS images.

## Features

- Browse upstream simplestream indices and inspect individual streams and products.
- Select products to mirror locally; artifacts are downloaded and stored under `data/simplestreams`.
- Upload custom kernels, initrds, and root file systems to publish bespoke images.
- Serve a fully compliant simplestream endpoint via `/simplestreams/streams/v1/index.json`.
- Manage the local image library with deletion support.

## Requirements

- Python 3.10+
- Node is not required; the front-end is static HTML/JS

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
uvicorn app.main:app --reload
```

Open `http://localhost:8000/` to access the UI. The simplestream index will be available under
`http://localhost:8000/simplestreams/streams/v1/index.json`.

## Project Layout

- `app/` — FastAPI application, database models, and services
- `frontend/` — Vanilla Framework based UI
- `data/simplestreams/` — local simplestream tree (created automatically)

## Tests

Unit tests can be added under `tests/`. Run them with:

```bash
pytest
```
