# Commerce Inventory & Order API

A FastAPI-based service for managing inventory SKUs, stock levels, reservations, and orders.

## Features

- SKU management with stock tracking
- Stock adjustment endpoints
- Reservation system with idempotency support
- Automatic expiration of stale reservations (300 seconds)
- Order creation from confirmed reservations
- Paginated order listing
- API key authentication for all mutations
- SQLite persistence

## API Endpoints

- `GET /health` - Health check (no auth required)
- `POST /skus` - Create a new SKU
- `POST /stock/adjust` - Adjust stock levels
- `POST /reservations` - Create a reservation
- `POST /reservations/{id}/confirm` - Confirm a reservation
- `POST /reservations/{id}/cancel` - Cancel a reservation
- `GET /orders` - List orders with pagination

## Authentication

All mutating endpoints (POST, PUT, DELETE) require an `X-API-Key` header with a valid API token.

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
pytest
```
