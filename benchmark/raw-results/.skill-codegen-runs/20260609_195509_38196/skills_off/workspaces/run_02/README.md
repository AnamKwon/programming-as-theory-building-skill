# Commerce Service

Inventory reservation and order orchestration API for a small commerce backend.

## Architecture

- **API Layer**: FastAPI endpoints with Pydantic validation
- **Service Layer**: Business logic for reservations, stock management, and order state
- **Repository Layer**: SQLAlchemy ORM with SQLite backend
- **Security**: API-key authentication for mutating endpoints

## Endpoints

### Health
- `GET /health` — Service health check

### SKU Management
- `POST /skus` — Create a new SKU (requires API key)
- `POST /stock/adjust` — Adjust inventory for a SKU (requires API key)

### Reservations
- `POST /reservations` — Create a reservation (tentative hold; requires API key)
- `POST /reservations/{reservation_id}/confirm` — Confirm reservation, convert to order (requires API key)
- `POST /reservations/{reservation_id}/cancel` — Cancel a pending reservation (requires API key)

### Orders
- `GET /orders` — List orders with pagination (requires API key)
- `GET /orders/{order_id}` — Get a single order

## Running

Install dependencies:
```bash
pip install -e ".[dev]"
```

Run the server:
```bash
uvicorn commerce_service.app:app --reload
```

Run tests:
```bash
pytest tests/ -v
```

## Design Notes

- **Idempotent Reservations**: Reservations are created with an idempotency key; retrying with the same key returns the existing reservation.
- **Reservation Expiry**: Unconfirmed reservations expire after a configurable TTL; attempting to confirm an expired reservation fails.
- **Stock Availability**: Reservations are only created if sufficient stock is available (not already reserved).
- **API Key**: Configurable via environment (default: `test-key`); health and read-only order endpoints do not require it.

## Testing

The test suite covers:
- Happy-path reservation and order flows
- Insufficient stock scenarios
- Idempotent reservation retry
- Expired reservation rejection
- Unauthorized mutation attempts
- Pagination for order listing
