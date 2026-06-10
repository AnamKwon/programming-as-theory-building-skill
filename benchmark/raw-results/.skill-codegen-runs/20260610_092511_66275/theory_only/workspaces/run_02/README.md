# Commerce Service

Inventory reservation and order orchestration API built with FastAPI and SQLite.

## Features

- **SKU Management:** Create and track products by SKU identifier
- **Stock Control:** Adjust available inventory with proper locking
- **Reservations:** Lock stock with automatic expiration (30 min default)
- **Orders:** Confirmed reservations become orders; support lookup with pagination
- **Idempotency:** Retry-safe operations via idempotency keys
- **Authentication:** API-key authentication for mutating endpoints
- **Validation:** Pydantic-based request/response validation

## Quick Start

```bash
pip install -e ".[dev]"
pytest
uvicorn commerce_service.app:app --reload
```

## API Overview

### Health
- `GET /health` — Service health check

### SKUs
- `POST /skus` — Create SKU (requires API key)
- `GET /skus/{sku_id}` — Get SKU details

### Stock
- `POST /stock/adjust` — Adjust inventory level (requires API key)

### Reservations
- `POST /reservations` — Reserve units (requires API key, idempotent)
- `GET /reservations/{reservation_id}` — Get reservation details
- `PATCH /reservations/{reservation_id}/confirm` — Confirm reservation, create order (requires API key, idempotent)
- `DELETE /reservations/{reservation_id}` — Cancel reservation (requires API key)

### Orders
- `GET /orders` — List orders (paginated; `skip`, `limit` query params)
- `GET /orders/{order_id}` — Get order details

## State Transitions

**Reservation:** `PENDING` → `CONFIRMED` → `COMPLETED` (or `EXPIRED`, `CANCELLED`)

**Order:** Created when reservation is confirmed; `CONFIRMED` → `COMPLETED`

## Architecture

- **models.py:** Pydantic request/response schemas and SQLAlchemy ORM models
- **repository.py:** SQLite access layer (CRUD operations)
- **service.py:** Business logic (stock checks, reservations, idempotency)
- **security.py:** API-key authentication
- **app.py:** FastAPI routes and dependency injection

## Database

SQLite database (`commerce.db`) created and migrated on startup.

## Error Handling

- `400 Bad Request` — Validation error or business rule violation
- `401 Unauthorized` — Missing or invalid API key
- `404 Not Found` — Resource not found
- `409 Conflict` — Insufficient stock or state conflict
- `500 Internal Server Error` — Unexpected failure
