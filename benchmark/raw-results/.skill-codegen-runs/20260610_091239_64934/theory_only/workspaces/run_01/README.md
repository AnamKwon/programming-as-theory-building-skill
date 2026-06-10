# Commerce Service

A production-grade inventory reservation and order orchestration API built with FastAPI, Pydantic, and SQLite.

## Features

- **SKU Management**: Create and manage product inventory with real-time stock tracking
- **Reservation System**: Reserve stock with automatic expiration to prevent indefinite holds
- **Order Orchestration**: Confirm reservations and create orders with state transitions
- **API Key Authentication**: Secure mutating endpoints with X-API-Key header
- **Idempotency**: Prevent duplicate operations using idempotency keys
- **Pagination**: List orders with configurable page size
- **Clear Error Handling**: Structured HTTP errors with meaningful messages

## Architecture

- **Service Layer**: Enforces business rules (stock availability, expiration, state transitions)
- **Repository Pattern**: Centralizes all SQLite database access
- **Pydantic Models**: Request/response validation and domain objects
- **FastAPI Routes**: Clean REST endpoints with dependency injection

## Quick Start

### Installation

```bash
pip install -e ".[dev]"
```

### Run the Server

```bash
uvicorn commerce_service.app:app --reload
```

Server runs on `http://localhost:8000`

### Run Tests

```bash
pytest tests/
```

## API Endpoints

### Health Check
- `GET /health` - Server health status

### SKU Management
- `POST /skus` - Create a new SKU (requires API key)
- `GET /skus/{sku_id}` - Get SKU details and stock levels
- `POST /skus/{sku_id}/adjust-stock` - Adjust stock by amount (requires API key)

### Reservations
- `POST /reservations` - Create a reservation with TTL (requires API key)
- `GET /reservations/{reservation_id}` - Get reservation details
- `POST /reservations/{reservation_id}/confirm` - Confirm a pending reservation (requires API key)
- `POST /reservations/{reservation_id}/cancel` - Cancel a reservation (requires API key)

### Orders
- `POST /orders` - Create an order from confirmed reservations (requires API key)
- `GET /orders/{order_id}` - Get order details
- `GET /orders` - List orders with pagination

## Authentication

All mutating endpoints require an `X-API-Key` header. Valid test keys:
- `test-api-key-123`
- `test-api-key-456`

## Example Workflow

```bash
# 1. Create a SKU
curl -X POST http://localhost:8000/skus \
  -H "X-API-Key: test-api-key-123" \
  -H "Content-Type: application/json" \
  -d '{"sku_id": "PROD-001", "initial_stock": 100}'

# 2. Create a reservation
curl -X POST http://localhost:8000/reservations \
  -H "X-API-Key: test-api-key-123" \
  -H "Content-Type: application/json" \
  -d '{
    "sku_id": "PROD-001",
    "quantity": 20,
    "idempotency_key": "user-request-123",
    "ttl_seconds": 300
  }'

# 3. Confirm the reservation
curl -X POST http://localhost:8000/reservations/RES-UUID/confirm \
  -H "X-API-Key: test-api-key-123" \
  -H "Content-Type: application/json" \
  -d '{"reservation_id": "RES-UUID", "idempotency_key": "confirm-123"}'

# 4. Create an order
curl -X POST http://localhost:8000/orders \
  -H "X-API-Key: test-api-key-123" \
  -H "Content-Type: application/json" \
  -d '{"reservation_ids": ["RES-UUID"], "idempotency_key": "order-123"}'

# 5. Get the order
curl http://localhost:8000/orders/ORDER-UUID
```

## Design Notes

**Idempotency:** Create and confirm operations are idempotent—retrying with the same key returns the same result without side effects.

**Expiration:** Pending reservations automatically expire after their TTL, releasing stock back to availability. Expired reservations cannot be confirmed.

**State Machine:** Reservations flow through `pending → confirmed → (order created)`. Orders flow through `pending → confirmed → completed/cancelled`.

**Stock Tracking:** Available stock and reserved stock are tracked separately to support accurate reservations without blocking availability updates.
