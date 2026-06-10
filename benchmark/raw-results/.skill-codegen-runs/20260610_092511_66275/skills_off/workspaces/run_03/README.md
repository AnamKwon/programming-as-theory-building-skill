# Commerce Service

Inventory reservation and order orchestration API for small commerce backends.

## Overview

This service manages:
- **SKU Creation**: Define products with initial stock levels.
- **Stock Adjustment**: Adjust inventory up or down.
- **Reservations**: Reserve stock with automatic expiration after 10 minutes.
- **Orders**: Confirm reservations into orders with proper state transitions.
- **Lookups**: Retrieve orders with pagination.

## Architecture

- **FastAPI**: Modern async web framework.
- **SQLAlchemy**: ORM for database abstraction.
- **SQLite**: Lightweight persistent storage.
- **Pydantic**: Request/response validation.
- **Repository Pattern**: Clean separation of data access.

## Quick Start

### Install

```bash
pip install -e ".[dev]"
```

### Run

```bash
python -m uvicorn commerce_service.app:app --reload
```

Server runs on `http://localhost:8000`. OpenAPI docs at `/docs`.

### Test

```bash
pytest tests/
```

## API Overview

All mutating endpoints require `X-API-Key: secret-key` header.

### Endpoints

- `GET /health` - Health check.
- `POST /api/skus` - Create SKU.
- `POST /api/stock/adjust` - Adjust stock.
- `POST /api/reservations` - Create reservation (idempotent).
- `POST /api/reservations/{id}/confirm` - Confirm reservation to order.
- `POST /api/reservations/{id}/cancel` - Cancel reservation.
- `GET /api/orders` - List orders (paginated).

## Data Model

**SKU**: Product with fixed stock level.
**Reservation**: Holds stock for a time window (10 min default), can become an Order.
**Order**: Confirmed reservation with final state.

Reservations transition: `PENDING` → (`CONFIRMED` or `CANCELLED` or `EXPIRED`).

## Idempotency

Reservation creation uses `idempotency_key` to prevent duplicate reservations for the same logical request.

## Error Handling

- `400 Bad Request`: Validation errors.
- `401 Unauthorized`: Missing/invalid API key.
- `404 Not Found`: Resource not found.
- `409 Conflict`: Business logic violation (e.g., insufficient stock).
- `500 Internal Server Error`: Unexpected failures.
