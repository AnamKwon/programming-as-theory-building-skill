# Commerce Service

A FastAPI-based inventory reservation and order orchestration API for small commerce backends.

## Features

- SKU management and stock tracking
- Inventory reservation with automatic expiration
- Idempotent reservation creation via idempotency keys
- Reservation confirmation and cancellation
- Order lookup with pagination
- API-key protected mutations
- SQLite persistence

## Running

```bash
# Install
pip install -e .

# Run server
uvicorn src.commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`. OpenAPI docs at `/docs`.

## Testing

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# With coverage
pytest --cov=src/commerce_service
```

## API Endpoints

- `GET /health` — health check
- `POST /skus` — create a SKU (requires API key)
- `POST /stock/adjust` — adjust stock (requires API key)
- `POST /reservations` — create a reservation (requires API key)
- `POST /reservations/{id}/confirm` — confirm a reservation (requires API key)
- `DELETE /reservations/{id}` — cancel a reservation (requires API key)
- `GET /orders` — list orders with pagination

Authentication: Include `X-API-Key: test-key-123` header for mutating endpoints.
