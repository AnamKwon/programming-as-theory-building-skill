# Commerce Inventory & Order API

A FastAPI-based inventory management and order processing system.

## Features

- SKU (Stock Keeping Unit) management with stock tracking
- Reservation system with idempotent guarantees
- Order confirmation and fulfillment workflow
- Automatic reservation expiration (300 seconds)
- Paginated order listing
- API token-based authentication for mutations

## Installation

```bash
pip install -e ".[dev]"
```

## Running the Server

```bash
uvicorn commerce_service.app:app --reload
```

## Testing

```bash
pytest tests/
```

## API Endpoints

- `GET /health` - Health check (no auth required)
- `POST /skus` - Create a new SKU with initial stock (requires token)
- `POST /stock/adjust` - Adjust stock levels (requires token)
- `POST /reservations` - Create a reservation (requires token)
- `POST /reservations/{id}/confirm` - Confirm a pending reservation (requires token)
- `POST /reservations/{id}/cancel` - Cancel a pending reservation (requires token)
- `GET /orders` - List orders with pagination (no auth required)

## Authentication

Mutating endpoints require an `X-API-Token` header with the configured token value.

Default token: `test-token-12345`
