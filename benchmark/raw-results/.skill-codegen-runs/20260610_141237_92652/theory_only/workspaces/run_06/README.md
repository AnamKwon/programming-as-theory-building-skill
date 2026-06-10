# Commerce Inventory & Order API

A FastAPI-based service for managing inventory SKUs, stock reservations, and order creation.

## Features

- SKU inventory management
- Stock reservation with idempotency
- Automatic expiration handling (300 seconds)
- Order creation from confirmed reservations
- Token-based API authentication
- SQLite backend

## Quick Start

```bash
# Install dependencies
pip install -e ".[dev]"

# Run the server
uvicorn commerce_service.app:app --reload

# Run tests
pytest tests/
```

## API Endpoints

- `GET /health` - Health check
- `POST /skus` - Create a new SKU with initial stock
- `POST /stock/adjust` - Adjust stock levels
- `POST /reservations` - Create a stock reservation
- `POST /reservations/{id}/confirm` - Confirm a reservation
- `POST /reservations/{id}/cancel` - Cancel a reservation
- `GET /orders` - List orders with pagination

## Authentication

All mutation endpoints (POST, PUT, DELETE) require an `X-API-Key` header with a valid token.
The default token is `test-key-123`.

## Database

SQLite database is created automatically on startup at `./commerce.db`.
