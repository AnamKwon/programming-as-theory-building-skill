# Commerce Service

A small commerce backend API for inventory reservation and order orchestration.

## Features

- **SKU Management**: Create and manage product SKUs
- **Stock Management**: Track inventory levels and adjustments
- **Reservation System**: Temporal holds on inventory with automatic expiration
- **Order Orchestration**: Reserve → confirm → deliver or cancel workflow
- **Idempotency**: Safe retries via idempotency keys
- **API Key Security**: Protected mutation endpoints

## Architecture

- **Models** (`models.py`): Domain entities (SKU, Stock, Reservation, Order) with Pydantic schemas
- **Repository** (`repository.py`): Data access layer with SQLAlchemy ORM
- **Service** (`service.py`): Business logic and invariant enforcement
- **API** (`app.py`): FastAPI endpoints with validation and error handling
- **Security** (`security.py`): API key authentication

## Getting Started

### Install

```bash
pip install -e ".[dev]"
```

### Run Server

```bash
uvicorn commerce_service.app:app --reload
```

Server runs on `http://localhost:8000`.

### Run Tests

```bash
pytest
```

## API Endpoints

### Health

- `GET /health` - Health check

### SKU Management

- `POST /skus` - Create SKU (requires API key)
- `GET /skus/{sku_id}` - Get SKU details

### Stock

- `POST /skus/{sku_id}/stock` - Adjust stock level (requires API key)
- `GET /skus/{sku_id}/stock` - Get current stock

### Reservations

- `POST /reservations` - Create reservation (requires API key)
- `GET /reservations/{reservation_id}` - Get reservation details
- `POST /reservations/{reservation_id}/confirm` - Confirm reservation (requires API key)
- `POST /reservations/{reservation_id}/cancel` - Cancel reservation (requires API key)

### Orders

- `GET /orders` - List orders with pagination (requires API key)
- `GET /orders/{order_id}` - Get order details

## Invariants

1. **No negative stock**: Stock level never goes below 0
2. **Reservation expiration**: Reservations auto-expire after TTL
3. **Idempotency**: Same idempotency key returns same result, never double-executes
4. **Order states**: pending → (confirmed OR cancelled)
5. **Stock consumption**: Confirmed orders hold reserved stock; cancelled orders release it

## Database

Uses SQLite with SQLAlchemy ORM. Database file: `commerce.db`

## Security

Mutation endpoints require `x-api-key` header. Set via `API_KEY` environment variable (default: `test-key`).
