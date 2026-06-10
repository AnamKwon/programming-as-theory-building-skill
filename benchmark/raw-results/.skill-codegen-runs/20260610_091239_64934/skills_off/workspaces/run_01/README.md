# Commerce Service

A production-grade inventory reservation and order orchestration API built with FastAPI.

## Features

- **SKU Management**: Create and manage product SKUs with stock levels
- **Inventory Reservation**: Reserve stock with automatic expiration
- **Order Management**: Orchestrate multi-item orders with state transitions
- **Idempotency**: Safely retry reservation requests with idempotency keys
- **API Key Authentication**: Secure mutation endpoints
- **Pagination**: Efficiently list large order datasets
- **SQLite Backend**: Lightweight persistent storage

## Quick Start

### Install dependencies
```bash
pip install -e ".[dev]"
```

### Run the server
```bash
uvicorn commerce_service.app:app --reload
```

Server runs at `http://localhost:8000`

### Run tests
```bash
pytest
```

## API Endpoints

### Health
- `GET /health` - Service health check

### SKUs
- `POST /skus` - Create a new SKU (requires API key)
- `POST /skus/{sku_id}/adjust-stock` - Adjust stock levels (requires API key)

### Reservations
- `POST /reservations` - Create a reservation (requires API key, includes idempotency key)
- `POST /reservations/{reservation_id}/confirm` - Confirm a reservation (requires API key)
- `POST /reservations/{reservation_id}/cancel` - Cancel a reservation (requires API key)

### Orders
- `GET /orders` - List orders with pagination
- `GET /orders/{order_id}` - Get order details

## Authentication

Mutation endpoints (`POST`) require an `X-API-Key` header. Default key is `test-key-123`.

```bash
curl -X POST http://localhost:8000/skus \
  -H "X-API-Key: test-key-123" \
  -H "Content-Type: application/json" \
  -d '{"name": "Widget", "quantity": 100}'
```

## Design

- **Service Layer**: Core business logic for reservations and stock management
- **Repository Layer**: Database abstraction for data persistence
- **Pydantic Models**: Request/response validation
- **SQLAlchemy ORM**: Type-safe database queries

The API enforces:
- Stock availability before reservation
- Idempotency for safe retries
- Reservation expiration (30-minute default)
- Proper state transitions (pending → confirmed → locked)
