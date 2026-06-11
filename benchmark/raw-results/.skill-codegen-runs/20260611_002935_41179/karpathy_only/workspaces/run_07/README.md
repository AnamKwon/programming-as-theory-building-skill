# Commerce Inventory & Order API

A FastAPI-based microservice for managing inventory SKUs, stock levels, reservations, and orders with idempotent operations and expiration handling.

## Features

- SKU and stock management
- Idempotent reservation system with automatic expiration
- Order creation and pagination
- API token-based authentication for mutations
- SQLite backend with repository pattern isolation

## Installation

```bash
pip install -e .[dev]
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
- `POST /skus` - Create SKU with initial stock
- `POST /stock/adjust` - Adjust stock levels
- `POST /reservations` - Create reservation (idempotent)
- `POST /reservations/{id}/confirm` - Confirm reservation
- `POST /reservations/{id}/cancel` - Cancel reservation
- `GET /orders` - List orders with pagination

All mutating endpoints (POST, PUT, DELETE) require `X-API-Key` header.
