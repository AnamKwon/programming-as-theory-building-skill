# Commerce Service

Inventory reservation and order orchestration API built with FastAPI.

## Features

- **SKU Management**: Create and manage product SKUs.
- **Stock Control**: Adjust inventory levels with transaction tracking.
- **Reservations**: Create, confirm, and cancel reservations with expiration handling.
- **Orders**: Place orders from confirmed reservations with state tracking.
- **Pagination**: Browse orders with offset/limit pagination.
- **API Security**: API key authentication for mutating endpoints.
- **Idempotency**: Duplicate requests with the same idempotency key are safely handled.

## Running Locally

```bash
# Install dependencies
pip install -e ".[dev]"

# Run server
uvicorn commerce_service.app:app --reload

# Run tests
pytest -v
```

## API Examples

```bash
# Health check
curl http://localhost:8000/health

# Create a SKU
curl -X POST http://localhost:8000/skus \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-key" \
  -d '{"sku_code": "PROD001", "name": "Product 1"}'

# Adjust stock
curl -X POST http://localhost:8000/stock/adjust \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-key" \
  -d '{"sku_code": "PROD001", "delta": 100}'

# Create reservation (idempotency key prevents duplicates)
curl -X POST http://localhost:8000/reservations \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-key" \
  -d '{"sku_code": "PROD001", "quantity": 5, "idempotency_key": "req-123"}'

# Confirm reservation
curl -X POST http://localhost:8000/reservations/1/confirm \
  -H "X-API-Key: test-key"

# List orders with pagination
curl "http://localhost:8000/orders?offset=0&limit=10"
```

## Database

Uses SQLite with the following tables:
- `skus`: Product definitions
- `stock`: Inventory levels
- `reservations`: Pending orders
- `orders`: Confirmed orders
- `order_items`: Order line items
