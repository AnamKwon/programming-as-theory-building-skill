# Commerce Service

A production-style inventory reservation and order orchestration API built with FastAPI, SQLAlchemy, and SQLite.

## Features

- **SKU Management**: Create and manage product SKUs with stock levels
- **Stock Adjustment**: Adjust inventory for SKUs
- **Reservation System**: Create, confirm, and cancel reservations with automatic expiration
- **Order Orchestration**: Manage orders with state transitions
- **Idempotency**: Built-in support for idempotent reservation creation
- **API Key Authentication**: Protect mutating endpoints with API keys
- **Pagination**: Browse orders with cursor-based pagination

## Installation

```bash
pip install -e .
pip install -e ".[dev]"  # For development
```

## Running the Service

```bash
python -m uvicorn commerce_service.app:app --reload
```

The service will be available at `http://localhost:8000` with interactive docs at `/docs`.

## Testing

```bash
pytest
pytest -v  # Verbose output
pytest -s  # Show print statements
```

## API Endpoints

### Health
- `GET /health` - Service health check

### SKUs
- `POST /skus` - Create a SKU (requires API key)
- `PATCH /skus/{sku_id}/stock` - Adjust stock level (requires API key)

### Reservations
- `POST /reservations` - Create a reservation (requires API key)
- `POST /reservations/{reservation_id}/confirm` - Confirm a reservation (requires API key)
- `POST /reservations/{reservation_id}/cancel` - Cancel a reservation (requires API key)

### Orders
- `GET /orders` - List orders with pagination
- `GET /orders/{order_id}` - Get order details

## Authentication

Protect mutating endpoints with the `X-API-Key` header:

```bash
curl -X POST http://localhost:8000/skus \
  -H "X-API-Key: test-key" \
  -H "Content-Type: application/json" \
  -d '{"sku_code": "PROD001", "initial_stock": 100}'
```

The default API key for development is `test-key`.
