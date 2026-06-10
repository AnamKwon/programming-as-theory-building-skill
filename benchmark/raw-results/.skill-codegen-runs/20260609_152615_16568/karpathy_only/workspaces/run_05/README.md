# Commerce Service

Inventory reservation and order orchestration API built with FastAPI, Pydantic, and SQLite.

## Features

- **Inventory Management**: Create SKUs and adjust stock levels
- **Reservation System**: Reserve stock with expiration windows
- **Order Orchestration**: Confirm reservations into orders with state tracking
- **Idempotency**: Replay-safe reservation creation via idempotency keys
- **API Security**: Key-based authentication for mutating endpoints
- **Pagination**: Efficient order lookup with limit/offset

## Quick Start

### Install

```bash
pip install -e ".[dev]"
```

### Run

```bash
uvicorn commerce_service.app:app --reload
```

API is available at `http://localhost:8000`.

### Test

```bash
pytest
```

## API Overview

**Public endpoints:**
- `GET /health` — liveness probe
- `GET /orders` — list orders (with pagination)

**Authenticated endpoints** (require `X-API-Key` header):
- `POST /skus` — create SKU
- `PATCH /skus/{sku_id}/stock` — adjust stock
- `POST /reservations` — create reservation
- `POST /reservations/{reservation_id}/confirm` — confirm reservation
- `DELETE /reservations/{reservation_id}` — cancel reservation

## Design

- **Models** (`models.py`): Pydantic schemas for requests/responses and SQLAlchemy ORM
- **Repository** (`repository.py`): Data access layer
- **Service** (`service.py`): Business logic (inventory rules, state transitions)
- **App** (`app.py`): FastAPI routes and dependency injection
- **Security** (`security.py`): API key validation

Database: SQLite at `commerce.db` (auto-created on startup)
