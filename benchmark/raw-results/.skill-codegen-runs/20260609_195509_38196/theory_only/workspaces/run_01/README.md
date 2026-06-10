# Commerce Service

A production-grade inventory reservation and order orchestration API built with FastAPI and SQLite.

## Design

The service enforces a clean separation of concerns:

- **Models** define Pydantic request/response schemas and SQLAlchemy ORM entities.
- **Repository** handles all database access, isolating SQLAlchemy from the domain.
- **Service** layer encodes business rules: stock availability, idempotency, reservation expiration, order state transitions.
- **API** endpoints expose operations through FastAPI with request validation and error handling.
- **Security** uses API keys to guard mutating operations.

## Architecture

```
API (FastAPI endpoints)
  ↓
Security (API key validation)
  ↓
Service (business logic: stock, reservations, orders)
  ↓
Repository (SQLAlchemy + SQLite)
```

## Getting Started

### Install

```bash
pip install -e .
pip install -e ".[test,dev]"
```

### Run

```bash
python -m uvicorn src.commerce_service.app:app --reload
```

Health check: `curl http://localhost:8000/health`

### Test

```bash
pytest
```

## API

All endpoints use JSON. Mutating endpoints require an `X-API-Key` header (default: `test-key`).

- `GET /health` — health check
- `POST /skus` — create SKU
- `GET /skus/{sku_id}` — get SKU details
- `POST /stock/adjust` — adjust stock level
- `POST /reservations` — create reservation (reserves inventory for a period)
- `POST /reservations/{reservation_id}/confirm` — confirm reservation (converts to order)
- `POST /reservations/{reservation_id}/cancel` — cancel reservation (releases reserved stock)
- `GET /orders?page=1&page_size=10` — list orders with pagination

## Domain Concepts

**SKU**: A stock keeping unit. Each SKU has a quantity on hand.

**Reservation**: A time-bounded claim on inventory. Expires after 30 minutes if not confirmed. Cannot be created if insufficient stock.

**Order**: The final committed state after confirming a reservation. Represents sold inventory.

**Idempotency**: Operations that create reservations or orders accept an idempotency key to prevent duplicates on retry.

## Database

SQLite in `commerce.db`. Schema is auto-created on startup.
