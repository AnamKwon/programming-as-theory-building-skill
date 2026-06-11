# Commerce Inventory & Order API

A FastAPI-based service for managing inventory SKUs, stock levels, reservations, and orders with idempotency and expiration checks.

## Setup

```bash
pip install -e ".[dev]"
```

## Running the API

```bash
uvicorn src.commerce_service.app:app --reload
```

## Running Tests

```bash
pytest tests/
```

## API Endpoints

- `GET /health` - Health check
- `POST /skus` - Create a new SKU
- `POST /stock/adjust` - Adjust stock levels
- `POST /reservations` - Create a reservation
- `POST /reservations/{id}/confirm` - Confirm a reservation
- `POST /reservations/{id}/cancel` - Cancel a reservation
- `GET /orders` - List orders (paginated)

## Authentication

All mutating endpoints (POST, PUT, DELETE) require an `X-API-Key` header.

Default test API key: `test-key-123`
