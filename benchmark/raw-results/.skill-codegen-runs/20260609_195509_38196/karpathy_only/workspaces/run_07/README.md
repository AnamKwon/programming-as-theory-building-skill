# Commerce Service

Inventory reservation and order orchestration API built with FastAPI, Pydantic, and SQLite.

## Features

- **SKU Management**: Create and manage product inventory
- **Reservation System**: Reserve stock with automatic expiration
- **Order Orchestration**: Confirm reservations into orders, track status
- **Idempotency**: Safe retry semantics with idempotency keys
- **API Security**: Key-based authentication for mutations
- **Pagination**: List orders with cursor-based pagination

## Quick Start

### Install Dependencies

```bash
pip install -e .
pip install -e ".[dev]"  # for development and testing
```

### Run the Server

```bash
uvicorn src.commerce_service.app:app --reload
```

Server runs on `http://localhost:8000`. Check `/docs` for interactive API docs.

### Run Tests

```bash
pytest
```

## API Endpoints

### Health Check
- `GET /health` - Service health status

### SKU Management
- `POST /skus` - Create a new SKU
- `PATCH /skus/{sku_id}/stock` - Adjust stock level

### Reservations
- `POST /reservations` - Create a reservation
- `POST /reservations/{reservation_id}/confirm` - Confirm reservation to order
- `POST /reservations/{reservation_id}/cancel` - Cancel reservation

### Orders
- `GET /orders` - List orders with pagination
- `GET /orders/{order_id}` - Get order details

## Authentication

Mutating endpoints require an `x-api-key` header. The example API key is `test-key-123`.

## Design Notes

- **Repository Pattern**: All database access through `repository.py`
- **Service Layer**: Business logic in `service.py` enforces stock rules and state transitions
- **Reservation Expiry**: Reservations expire after 30 minutes if not confirmed
- **Idempotency**: Duplicate reservation requests with the same key return the same result
