# Commerce Service

A production-grade inventory reservation and order orchestration API built with FastAPI.

## Features

- SKU and stock management
- Reservation system with expiration
- Order confirmation and fulfillment
- Idempotency for reservation creation
- API key authentication for mutations
- Pagination support for order listing
- SQLite persistence

## Setup

Install dependencies:
```bash
pip install -e ".[dev]"
```

Run the service:
```bash
uvicorn commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`. Documentation at `http://localhost:8000/docs`.

## Testing

Run tests:
```bash
pytest
```

## API Endpoints

- `GET /health` - Health check
- `POST /skus` - Create a SKU
- `POST /skus/{sku_id}/adjust` - Adjust stock for a SKU
- `POST /reservations` - Create a reservation
- `POST /reservations/{id}/confirm` - Confirm a pending reservation
- `POST /reservations/{id}/cancel` - Cancel a reservation
- `GET /orders` - List confirmed orders with pagination

All mutation endpoints require an `X-API-Key` header.
