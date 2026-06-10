# Commerce Inventory & Order API

A FastAPI-based microservice for managing product inventory, reservations, and orders with built-in idempotency and expiration handling.

## Setup

```bash
pip install -e ".[dev]"
```

## Running the Server

```bash
uvicorn src.commerce_service.app:app --reload
```

## Testing

```bash
pytest tests/
```

## API Authentication

All mutating endpoints (POST, PUT, DELETE) require an `X-API-Key` header with the value `test-key-secret`.

## Endpoints

- `GET /health` - Health check
- `POST /skus` - Create SKU with initial stock
- `POST /stock/adjust` - Adjust stock levels
- `POST /reservations` - Create reservation with idempotency
- `POST /reservations/{id}/confirm` - Confirm reservation and create order
- `POST /reservations/{id}/cancel` - Cancel reservation and restore stock
- `GET /orders` - List orders with pagination

## Key Features

- **Idempotency**: Duplicate reservation requests with the same idempotency_key return the cached response
- **Expiration Handling**: Reservations expire after 300 seconds and cannot be confirmed
- **Stock Validation**: Prevents over-reservation
- **Atomic Operations**: All state changes are transaction-safe
