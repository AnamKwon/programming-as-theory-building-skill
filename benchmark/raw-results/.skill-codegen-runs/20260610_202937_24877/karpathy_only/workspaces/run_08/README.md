# Commerce Inventory & Order API

A FastAPI-based inventory management and order processing system with stock reservations, idempotent operations, and expiration handling.

## Features

- SKU management with stock tracking
- Stock adjustment (increment/decrement)
- Idempotent reservation system with 300-second expiration
- Order creation and pagination
- API token authentication for mutations
- SQLite persistence

## Installation

```bash
pip install -e ".[dev]"
```

## Running

```bash
uvicorn src.commerce_service.app:app --reload
```

Set the `API_KEY` environment variable (default: "test-key-123").

## Testing

```bash
pytest tests/
```

## API Endpoints

- `GET /health` - Health check
- `POST /skus` - Create SKU with initial stock
- `POST /stock/adjust` - Adjust stock level
- `POST /reservations` - Create reservation with idempotency
- `POST /reservations/{id}/confirm` - Confirm reservation and create order
- `POST /reservations/{id}/cancel` - Cancel reservation and restore stock
- `GET /orders` - Paginated order list
