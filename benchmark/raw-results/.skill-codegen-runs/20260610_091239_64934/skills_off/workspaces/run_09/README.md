# Commerce Service

Inventory reservation and order orchestration API built with FastAPI, Pydantic, and SQLite.

## Features

- SKU (Stock Keeping Unit) management
- Real-time stock tracking with reservation support
- Idempotent reservation creation with automatic expiration
- Order state machine (pending → confirmed → completed)
- API-key authentication on mutating endpoints
- Pagination for order listing
- Production-grade error handling and validation

## Running

Install dependencies:
```bash
pip install -e ".[dev]"
```

Run the service:
```bash
uvicorn commerce_service.app:app --reload
```

Run tests:
```bash
pytest
```

## API

### Health
- `GET /health` — Service health check

### SKUs
- `POST /skus` — Create a new SKU
- `POST /skus/{sku_id}/stock` — Adjust stock level (requires API key)

### Reservations
- `POST /reservations` — Create a reservation with idempotency (requires API key)
- `POST /reservations/{reservation_id}/confirm` — Confirm a pending reservation (requires API key)
- `POST /reservations/{reservation_id}/cancel` — Cancel a reservation (requires API key)

### Orders
- `GET /orders` — List orders with pagination
- `GET /orders/{order_id}` — Get order details

## Authentication

Mutating endpoints require `X-API-Key` header. Default key is `test-key-123`.
