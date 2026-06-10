# Commerce Service

A FastAPI-based inventory reservation and order orchestration service for small commerce backends.

## Features

- SKU management with stock tracking
- Reservation system with expiration
- Order orchestration with state transitions
- Idempotency key support for safe retries
- API key authentication for mutations
- Pagination for order queries
- SQLite persistence

## Running

```bash
# Install dependencies
pip install -e .

# Run the server
uvicorn commerce_service.app:app --reload
```

The service starts on `http://localhost:8000`. Health check available at `GET /health`.

## Testing

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## API Endpoints

### Public
- `GET /health` - Health check

### SKU Management
- `POST /skus` - Create SKU (requires API key)
- `PATCH /skus/{sku_id}/stock` - Adjust stock level (requires API key)

### Reservations
- `POST /reservations` - Create reservation (requires API key, supports idempotency)
- `POST /reservations/{reservation_id}/confirm` - Confirm reservation → order (requires API key)
- `POST /reservations/{reservation_id}/cancel` - Cancel reservation (requires API key)

### Orders
- `GET /orders` - List orders with pagination (query params: skip, limit)

## Configuration

API key is passed via `X-API-Key` header for all mutation endpoints. Default: `test-key-12345`.
