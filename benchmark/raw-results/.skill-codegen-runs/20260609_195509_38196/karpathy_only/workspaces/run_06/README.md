# Commerce Service

Inventory reservation and order orchestration API for small commerce backends.

## Features

- SKU creation and stock management
- Inventory reservations with expiration
- Idempotent reservation operations
- Order confirmation and lifecycle tracking
- API key authentication for mutations
- Pagination for order queries
- Health checks and monitoring

## Getting Started

### Install dependencies

```bash
pip install -e .
pip install -e ".[dev]"
```

### Run the service

```bash
uvicorn src.commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`.

Health check: `curl http://localhost:8000/health`

### Run tests

```bash
pytest
```

## API Documentation

### Authentication

Mutating endpoints (POST, PATCH, DELETE) require an `X-API-Key` header:

```bash
curl -X POST http://localhost:8000/skus \
  -H "X-API-Key: test-key-123" \
  -H "Content-Type: application/json" \
  -d '{"sku": "PROD-001", "stock": 100}'
```

### Endpoints

#### Health

- `GET /health` — Service health check

#### SKUs

- `POST /skus` — Create a new SKU
- `GET /skus/{sku_code}` — Get SKU details
- `POST /skus/{sku_code}/adjust-stock` — Adjust stock level

#### Reservations

- `POST /reservations` — Create a new reservation
- `PATCH /reservations/{reservation_id}/confirm` — Confirm a reservation
- `DELETE /reservations/{reservation_id}` — Cancel a reservation

#### Orders

- `GET /orders` — List orders with pagination

## Design Notes

- **Repository Pattern**: Database access is isolated in the repository layer for testability.
- **Service Layer**: Business logic for reservations, confirmations, and state transitions.
- **Idempotency**: Reservation creation and confirmation use idempotency keys to prevent duplicates.
- **Expiration**: Reservations expire after 10 minutes if not confirmed.
- **State Transitions**: Reservations follow strict state paths (pending → confirmed or cancelled).
