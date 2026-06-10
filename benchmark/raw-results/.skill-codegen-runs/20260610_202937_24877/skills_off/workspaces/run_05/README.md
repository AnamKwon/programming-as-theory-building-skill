# Commerce Inventory & Order API

A FastAPI-based inventory and order management service with stock reservations, idempotent operations, and expiration handling.

## Features

- SKU management with stock tracking
- Reservation system with idempotency support
- Automatic reservation expiration (300 seconds)
- Order creation from confirmed reservations
- Paginated order retrieval
- API token-based authentication for mutations

## Installation

```bash
pip install -e .
pip install -e ".[dev]"
```

## Running the Service

```bash
uvicorn src.commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`.

## Running Tests

```bash
pytest tests/
```

## API Endpoints

### Health Check
- `GET /health` - Service health status (no auth required)

### SKU Management
- `POST /skus` - Create a new SKU with initial stock

### Stock Operations
- `POST /stock/adjust` - Adjust stock levels for a SKU

### Reservations
- `POST /reservations` - Create a new reservation with idempotency support
- `POST /reservations/{id}/confirm` - Confirm a pending reservation
- `POST /reservations/{id}/cancel` - Cancel a pending reservation

### Orders
- `GET /orders` - List orders with pagination

## Authentication

Mutating endpoints (POST, PUT, DELETE) require an `X-API-Key` header with a valid token.

Default API key: `test-api-key-secret`
