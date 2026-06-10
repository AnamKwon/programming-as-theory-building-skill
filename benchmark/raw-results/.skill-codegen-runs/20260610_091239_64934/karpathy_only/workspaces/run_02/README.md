# Commerce Service

A FastAPI-based inventory reservation and order orchestration service.

## Features

- **Inventory Management**: Create SKUs and manage stock levels
- **Reservation System**: Create, confirm, and cancel reservations with expiration
- **Order Tracking**: Look up orders with pagination
- **Idempotency**: Built-in support for idempotent operations
- **API Security**: API-key authentication for mutating endpoints
- **Repository Pattern**: Clean separation between service logic and data access

## Quick Start

### Install Dependencies

```bash
pip install -e ".[dev]"
```

### Run Server

```bash
uvicorn src.commerce_service.app:app --reload
```

Server runs on `http://localhost:8000`. API docs available at `/docs`.

### Run Tests

```bash
pytest
```

## API Endpoints

### Health
- `GET /health` - Health check

### SKUs
- `POST /skus` - Create a SKU (requires API key)
- `GET /skus/{sku_id}` - Get SKU details

### Stock
- `POST /stock/adjust` - Adjust stock level (requires API key)

### Reservations
- `POST /reservations` - Create a reservation (requires API key)
- `POST /reservations/{reservation_id}/confirm` - Confirm a reservation (requires API key)
- `POST /reservations/{reservation_id}/cancel` - Cancel a reservation (requires API key)

### Orders
- `GET /orders` - List orders with pagination (requires API key)
- `GET /orders/{order_id}` - Get order details (requires API key)

## Authentication

Pass the API key in the `X-API-Key` header for mutating endpoints:

```bash
curl -X POST http://localhost:8000/skus \
  -H "X-API-Key: secret-key" \
  -H "Content-Type: application/json" \
  -d '{"sku_id": "WIDGET-001", "name": "Widget", "unit_price": 19.99}'
```

Default API key is `secret-key` (configurable via environment).

## Architecture

- **app.py**: FastAPI application with route handlers
- **models.py**: Pydantic request/response schemas
- **service.py**: Business logic and reservation rules
- **repository.py**: SQLite data access layer
- **security.py**: API key authentication dependency

## Design Principles

- Service layer enforces invariants (stock availability, reservation expiration, state transitions)
- Repository hides database details behind a clean interface
- Pydantic validates all input at the boundary
- Clear HTTP error responses for all failure modes
- Idempotent reservation creation via idempotency keys
