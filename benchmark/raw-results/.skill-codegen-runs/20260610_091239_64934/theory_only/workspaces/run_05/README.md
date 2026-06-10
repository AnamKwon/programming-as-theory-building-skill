# Commerce Service

A production-style inventory reservation and order orchestration API built with FastAPI, Pydantic, and SQLite.

## Features

- **SKU Management**: Create and manage product SKUs with stock quantities.
- **Reservations**: Hold inventory with automatic expiration (default 15 minutes).
- **Order Lifecycle**: Confirm reservations into orders with state tracking (CREATED → CONFIRMED → SHIPPED/CANCELLED).
- **Idempotency**: Reservation creation via idempotency keys prevents duplicate holds.
- **API Key Security**: Mutating endpoints require valid API key header.
- **Pagination**: Order listing supports limit/offset pagination.

## API Endpoints

### Public
- `GET /health` — Health check
- `GET /orders` — List orders (paginated)

### Authenticated (require `X-API-Key` header)
- `POST /skus` — Create a SKU
- `POST /skus/{sku_id}/adjust-stock` — Adjust stock level
- `POST /reservations` — Create a reservation (idempotency key required)
- `POST /reservations/{reservation_id}/confirm` — Confirm a reservation into an order
- `POST /reservations/{reservation_id}/cancel` — Cancel a reservation

## Installation

```bash
pip install -e ".[dev]"
```

## Running

```bash
uvicorn commerce_service.app:app --reload
```

## Testing

```bash
pytest tests/ -v
```

## Design Notes

- **Service Layer**: All business rules (stock validation, state transitions, expiration) live in the service layer, not in routes.
- **Repository Pattern**: Database access is behind a clean repository boundary with no ORM.
- **Pydantic Boundary**: Request validation happens at the HTTP boundary; domain logic is decoupled.
- **Minimal**: No speculative features; design is built for the stated requirements only.
