# Commerce Inventory & Order API

A FastAPI-based microservice for managing inventory SKUs, reservations, and orders with idempotency and expiration enforcement.

## Features

- SKU management with stock tracking
- Reservation system with idempotency and 300-second expiration
- Order creation and pagination
- Token-based authentication for mutating endpoints
- SQLite backend with repository pattern
- Full pytest test coverage

## Installation

```bash
pip install -e .
pip install -e ".[dev]"
```

## Running

```bash
uvicorn commerce_service.app:app --reload
```

## Testing

```bash
pytest tests/
```

## API Endpoints

- `GET /health` - Health check
- `POST /skus` - Create SKU
- `POST /stock/adjust` - Adjust stock level
- `POST /reservations` - Create reservation
- `POST /reservations/{id}/confirm` - Confirm reservation
- `POST /reservations/{id}/cancel` - Cancel reservation
- `GET /orders` - List orders (paginated)

All POST/PUT/DELETE endpoints require `X-API-Token` header.
