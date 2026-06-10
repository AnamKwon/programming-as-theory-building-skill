# Commerce Service

Inventory reservation and order orchestration API.

## Features

- SKU management with stock tracking
- Reservation system with idempotency and expiration
- Order creation and state transitions
- API key authentication for mutations
- Paginated order lookup
- SQLite storage with SQLAlchemy ORM

## Installation

```bash
pip install -e .
pip install -e ".[dev]"
```

## Running

```bash
python -m uvicorn commerce_service.app:app --reload
```

Health check: `GET http://localhost:8000/health`

## API Key

Set the `X-API-Key` header to `test-key` (configurable via `API_KEY` env var) for mutating endpoints.

## Testing

```bash
pytest
```
