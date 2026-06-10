# Commerce Inventory & Order API

A FastAPI-based inventory management and order processing service with reservation support, idempotency, and expiration handling.

## Features

- SKU management with stock tracking
- Reservation system with idempotency keys
- Stock adjustment and validation
- Order creation from confirmed reservations
- Automatic expiration of old reservations (300 seconds)
- API token authentication on mutating endpoints
- Paginated order retrieval

## Setup

```bash
pip install -e ".[dev]"
```

## Running

```bash
uvicorn commerce_service.app:app --reload
```

## Testing

```bash
pytest
```

## API Endpoints

- `GET /health` - Health check
- `POST /skus` - Create SKU
- `POST /stock/adjust` - Adjust stock levels
- `POST /reservations` - Create reservation (with idempotency)
- `POST /reservations/{id}/confirm` - Confirm reservation
- `POST /reservations/{id}/cancel` - Cancel reservation
- `GET /orders` - List orders (paginated)

## Authentication

Mutating endpoints require an `X-API-Key` header with the value `test-api-key`.
