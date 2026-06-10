# Commerce Service

Inventory reservation and order orchestration API for small commerce backends.

## Features

- SKU management with stock tracking
- Idempotent reservation creation with automatic expiration
- Order creation and confirmation workflows
- Pagination support for order lookups
- API-key authentication for mutations
- SQLite persistence
- Comprehensive test coverage

## Running the Service

```bash
pip install -e ".[dev]"
uvicorn src.commerce_service.app:app --reload
```

The service will be available at `http://localhost:8000`. API documentation is at `/docs`.

## Testing

```bash
pytest tests/
```

## API Endpoints

- `GET /health` — Health check
- `POST /skus` — Create a SKU
- `POST /skus/{sku_id}/stock/adjust` — Adjust stock for a SKU
- `POST /reservations` — Create a reservation (requires API key)
- `POST /reservations/{reservation_id}/confirm` — Confirm a reservation (requires API key)
- `POST /reservations/{reservation_id}/cancel` — Cancel a reservation (requires API key)
- `GET /orders` — List orders with pagination (requires API key)

## Authentication

Mutating endpoints require an `X-API-Key` header. The default test key is `test-key-123`.

## Domain Rules

- Reservations expire after 15 minutes if not confirmed
- Idempotency keys prevent duplicate reservations within the same minute
- Orders transition through states: pending → confirmed → completed
- Stock availability is checked at reservation time
