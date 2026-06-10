# Commerce Service

A production-style inventory reservation and order orchestration API built with FastAPI, Pydantic, and SQLite.

## Features

- **SKU Management**: Create and manage product stock levels
- **Reservation System**: Reserve items with automatic expiration after 15 minutes
- **Idempotency**: Duplicate requests with the same idempotency key return the same result
- **Order Orchestration**: Confirm reservations into orders and track order status
- **API Key Security**: Protect mutating endpoints with API key authentication
- **Pagination**: Efficient order lookup with cursor-based pagination

## Architecture

- **API Layer** (`app.py`): FastAPI endpoints with request/response validation
- **Service Layer** (`service.py`): Business logic and invariant enforcement
- **Repository Layer** (`repository.py`): Data access and persistence
- **Models** (`models.py`): Pydantic request/response models
- **Security** (`security.py`): API key authentication

## API Endpoints

### Health
- `GET /health` – Service health check

### SKUs
- `POST /skus` – Create a SKU (requires API key)
- `GET /skus/{sku_id}` – Get SKU details

### Stock Management
- `POST /stock/{sku_id}/adjust` – Adjust stock level (requires API key)
- `GET /stock/{sku_id}` – Get current stock

### Reservations
- `POST /reservations` – Create a reservation (requires API key, idempotency key)
- `POST /reservations/{reservation_id}/confirm` – Confirm a reservation (requires API key)
- `POST /reservations/{reservation_id}/cancel` – Cancel a reservation (requires API key)

### Orders
- `GET /orders` – List orders with pagination (cursor-based)
- `GET /orders/{order_id}` – Get order details

## Running

```bash
pip install -e .
pip install -e ".[dev]"

# Start the service
uvicorn commerce_service.app:app --reload

# Run tests
pytest
```

## Authorization

Provide the API key in the `X-API-Key` header for mutating endpoints:
```
X-API-Key: test-key-12345
```

## Data Model

- **SKU**: Product identifier with name
- **Stock**: Inventory level tied to a SKU
- **Reservation**: Temporary hold on stock, expires after 15 minutes
- **Order**: Confirmed purchase created from a reservation

## Invariants

- Stock never goes negative
- Reservations cannot exceed available stock
- Expired reservations are rejected
- Idempotency keys prevent duplicate operations
- Only authenticated requests can mutate data
