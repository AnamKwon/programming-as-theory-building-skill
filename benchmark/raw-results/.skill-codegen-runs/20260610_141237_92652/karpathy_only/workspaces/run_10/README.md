# Commerce Inventory & Order API

A FastAPI-based service for managing inventory SKUs, reservations, and orders with idempotency and expiration handling.

## Installation

```bash
pip install -e ".[dev]"
```

## Running the Service

```bash
uvicorn src.commerce_service.app:app --reload
```

The service will be available at `http://localhost:8000`.

## API Endpoints

### Health Check
- `GET /health` - No authentication required

### SKU Management
- `POST /skus` - Create a new SKU with initial stock (requires API token)
- `POST /stock/adjust` - Adjust stock levels for a SKU (requires API token)

### Reservations
- `POST /reservations` - Create a reservation (requires API token)
  - Validates idempotency key
  - Checks sufficient stock availability
- `POST /reservations/{id}/confirm` - Confirm a pending reservation (requires API token)
  - Enforces 300-second expiration window
  - Creates corresponding order
- `POST /reservations/{id}/cancel` - Cancel a pending reservation (requires API token)
  - Restores reserved stock

### Orders
- `GET /orders` - List orders with pagination (page, size parameters)

## Authentication

All mutating endpoints (POST) require an `Authorization: Bearer <token>` header. The default token for testing is `test-token-secret`.

## Running Tests

```bash
pytest tests/
```

## Key Features

- **Idempotency**: Repeated requests with the same `idempotency_key` return cached results
- **Expiration**: Reservations expire 300 seconds after creation
- **Stock Management**: Atomic stock adjustments and restoration on cancellation/expiration
- **Pagination**: Order listing supports page-based pagination
