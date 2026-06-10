# Commerce Service

A FastAPI-based inventory reservation and order orchestration API for small commerce backends.

## Features

- **Inventory Management**: Create SKUs and adjust stock levels
- **Reservation System**: Create, confirm, and cancel reservations with automatic expiration
- **Idempotency**: Retry-safe reservation creation using idempotency keys
- **Order Orchestration**: Track orders and manage state transitions
- **API Security**: API-key authentication for mutating endpoints
- **Pagination**: Paginated order lookup with limit/offset

## Setup

```bash
pip install -e ".[dev]"
```

## Run

```bash
python -m uvicorn src.commerce_service.app:app --reload
```

## Test

```bash
pytest tests/
```

## API Endpoints

### Health Check
- `GET /health` - Service health check

### SKUs
- `POST /skus` - Create a SKU (requires API key)
- `GET /skus/{sku_id}` - Get SKU details

### Stock
- `POST /stock/adjust` - Adjust stock level (requires API key)

### Reservations
- `POST /reservations` - Create a reservation (requires API key)
- `POST /reservations/{reservation_id}/confirm` - Confirm a reservation (requires API key)
- `POST /reservations/{reservation_id}/cancel` - Cancel a reservation (requires API key)

### Orders
- `GET /orders` - List orders with pagination
- `GET /orders/{order_id}` - Get order details

## Authentication

Mutating endpoints (POST/DELETE) require an `X-API-Key` header. Default test key: `test-key-123`.
