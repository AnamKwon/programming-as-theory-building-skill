# Commerce Service

A FastAPI-based inventory reservation and order orchestration API for small commerce backends.

## Features

- **Inventory Management:** Create SKUs and adjust stock levels
- **Reservation System:** Temporary holds on inventory with expiration (30-second TTL)
- **Order Confirmation:** Convert reservations to finalized orders
- **Idempotency:** Duplicate requests with the same key return the same result
- **API Key Auth:** Mutations protected with simple API key validation
- **Pagination:** Order lookup with configurable limits and offsets
- **SQLite Backend:** Lightweight persistent storage with ACID semantics

## Running

```bash
pip install -e ".[dev]"
uvicorn commerce_service.app:app --reload
```

Server runs on `http://localhost:8000`.

## API Overview

### Health Check
- `GET /health` — Service health status

### SKU Management
- `POST /skus` — Create a SKU (requires API key)
- `POST /inventory/{sku}/adjust` — Adjust stock (requires API key)

### Reservations
- `POST /reservations` — Reserve units (requires API key)
- `POST /reservations/{reservation_id}/confirm` — Confirm reservation into order (requires API key)
- `POST /reservations/{reservation_id}/cancel` — Cancel a reservation (requires API key)

### Orders
- `GET /orders` — Lookup orders with pagination

## API Key

Pass `X-API-Key` header on mutating endpoints. Default key for testing: `test-key-12345`.

## Testing

```bash
pytest tests/
```

Tests cover:
- Happy path (create, reserve, confirm)
- Insufficient stock rejection
- Idempotent retry
- Expired reservation rejection
- Unauthorized mutation
- Order pagination

## Design

**Repository Layer:** SQLite operations ensure atomic stock accounting.

**Service Layer:** Business rules enforce stock availability, reservation expiration, idempotency, and state transitions.

**Invariant:** `total_stock = on_hand + reserved` across all SKUs.
