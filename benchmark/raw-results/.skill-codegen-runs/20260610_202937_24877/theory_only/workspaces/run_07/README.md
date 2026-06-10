# Commerce Inventory & Order API

A FastAPI-based inventory and order management system with SQLite persistence.

## Features

- SKU management with stock tracking
- Stock adjustments
- Reservation system with idempotency
- Reservation confirmation with expiration checks
- Order tracking with pagination
- API token-based authentication for mutating operations

## Setup

```bash
pip install -e .
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
- `POST /stock/adjust` - Adjust stock levels
- `POST /reservations` - Create reservation
- `POST /reservations/{id}/confirm` - Confirm reservation
- `POST /reservations/{id}/cancel` - Cancel reservation
- `GET /orders` - List orders with pagination

## Authentication

Mutating endpoints require `X-API-Key` header with valid token.
