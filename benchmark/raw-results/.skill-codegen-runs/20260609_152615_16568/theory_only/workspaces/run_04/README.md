# Commerce Service

A production-style inventory reservation and order orchestration API for small commerce backends.

## Overview

This service manages inventory stock, reservations, and order confirmation. Key features:

- **SKU Management**: Create and manage products with stock levels
- **Reservation Lifecycle**: Reserve inventory with automatic expiration (15 minutes)
- **Idempotency**: Duplicate reservation requests with the same idempotency key return the same reservation
- **Stock Protection**: Prevents overselling with reservation-aware availability tracking
- **Order Tracking**: Confirm reservations into orders and retrieve order history with pagination
- **API Security**: Requires API key for all mutation endpoints

## Architecture

The service follows a layered architecture:

- **Models** (`models.py`): Pydantic request/response schemas and SQLAlchemy ORM models
- **Repository** (`repository.py`): Data access layer providing storage abstraction
- **Service** (`service.py`): Domain logic enforcing business rules and invariants
- **Security** (`security.py`): API key validation for mutation endpoints
- **App** (`app.py`): FastAPI routes and HTTP boundary

## Installation

```bash
pip install -e .
```

For development:

```bash
pip install -e ".[dev]"
```

## Running

Start the server:

```bash
uvicorn src.commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000` with interactive docs at `/docs`.

## API Endpoints

### Health Check

```
GET /health
```

Returns service status and version.

### SKU Management

Create a SKU:
```
POST /skus
Headers: X-API-Key: <key>
Body: {"sku": "PROD-001", "stock": 100}
```

Get SKU details:
```
GET /skus/{sku_id}
```

Adjust stock:
```
PATCH /skus/{sku_id}/stock
Headers: X-API-Key: <key>
Body: {"delta": 50}
```

### Reservations

Create a reservation (holds stock for 15 minutes):
```
POST /reservations
Headers: X-API-Key: <key>
Body: {
  "sku_id": 1,
  "quantity": 10,
  "idempotency_key": "unique-key"
}
```

Get reservation details:
```
GET /reservations/{reservation_id}
```

Confirm a reservation (transitions to order):
```
POST /reservations/{reservation_id}/confirm
Headers: X-API-Key: <key>
Body: {}
```

Cancel a reservation (releases stock):
```
POST /reservations/{reservation_id}/cancel
Headers: X-API-Key: <key>
Body: {}
```

### Orders

Get order by order ID:
```
GET /orders/{order_id}
```

List orders with pagination:
```
GET /orders?page=1&page_size=10
```

## Key Invariants

1. **Idempotency**: Multiple requests with the same `idempotency_key` for the same SKU return the same reservation without duplicating stock allocation.

2. **Stock Availability**: A reservation can only be created if `available = stock - reserved >= quantity`.

3. **Reservation Expiration**: Pending reservations automatically expire after 15 minutes. Expired reservations release their allocated stock and cannot be confirmed.

4. **Immutable Orders**: Once a reservation is confirmed, it becomes an order and cannot be cancelled. Only pending reservations can be cancelled.

5. **API Security**: All mutation endpoints (POST, PATCH) require a valid API key in the `X-API-Key` header.

## Testing

Run all tests:

```bash
pytest
```

Run specific test file:

```bash
pytest tests/test_service.py
pytest tests/test_api.py
```

Run with coverage:

```bash
pytest --cov=src/commerce_service tests/
```

Test coverage includes:

- Happy path: SKU creation, reservation, confirmation, cancellation
- Insufficient stock: Rejected reservation when stock unavailable
- Idempotent retry: Same idempotency key returns existing reservation
- Reservation expiration: Expired reservations rejected and stock released
- Immutable orders: Confirmed reservations cannot be cancelled
- Unauthorized access: Missing or invalid API key returns 401/403
- Pagination: Order list with correct page calculation

## Database

The service uses SQLite by default. To change the database URL:

```bash
export DATABASE_URL="postgresql://user:password@localhost/commerce"
```

Database schema is automatically created on startup.

## Error Responses

- **400 Bad Request**: Invalid input, validation errors
- **401 Unauthorized**: Missing API key
- **403 Forbidden**: Invalid API key
- **404 Not Found**: SKU, reservation, or order not found
- **409 Conflict**: Insufficient stock for reservation
- **410 Gone**: Reservation expired

## Design Notes

- **Service Layer Encapsulation**: Business rules and invariants live in the service layer, not in the HTTP layer.
- **Repository Abstraction**: All database access goes through the repository, making the service testable without a real database.
- **Stock Calculation**: Available stock is calculated as `stock - reserved` rather than tracking separately, preventing inconsistency.
- **Minimal Speculation**: No unused hooks, queues, or providers. All code directly serves the stated requirements.
- **Clear Domain Model**: Reservation and Order share the same table but distinct lifecycle: pending/expired reservations vs. confirmed orders.

## License

MIT
