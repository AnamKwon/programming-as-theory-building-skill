# Commerce Service

Inventory reservation and order orchestration API built with FastAPI.

## Quick Start

### Installation

```bash
pip install -e ".[dev]"
```

### Run the Server

```bash
python -m uvicorn commerce_service.app:app --reload
```

The server will start on `http://localhost:8000`.

### Run Tests

```bash
pytest tests/
```

## API Overview

All mutation endpoints require an `X-API-Key` header. Use the default key `test-key` for development.

### Public Endpoints

- `GET /health` — Health check
- `GET /orders` — List orders with pagination

### Protected Endpoints (require API key)

- `POST /skus` — Create SKU
- `POST /stock/adjust` — Adjust stock for a SKU
- `POST /reservations` — Create a reservation for inventory
- `POST /reservations/{id}/confirm` — Confirm a reservation (creates order)
- `POST /reservations/{id}/cancel` — Cancel a reservation

## Database

Uses SQLite (`:memory:` by default, configurable via `DATABASE_URL` env var).

## Architecture

- **app.py** — FastAPI application and endpoint definitions
- **models.py** — Pydantic request/response schemas
- **service.py** — Business logic and state transitions
- **repository.py** — Data access layer (SQLAlchemy ORM)
- **security.py** — API key validation
- **tests/** — Unit and integration tests
