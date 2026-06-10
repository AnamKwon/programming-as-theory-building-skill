# Commerce Service

Inventory reservation and order orchestration API for e-commerce backends.

## Features

- **SKU Management**: Create and track product inventory
- **Stock Adjustment**: Add or remove stock
- **Reservations**: Temporary holds on inventory with automatic expiration
- **Order Orchestration**: Confirm reservations into orders with state transitions
- **Idempotency**: Prevent duplicate orders via idempotency keys
- **API Security**: Key-based authentication for mutations
- **Pagination**: Efficient order listing

## Quick Start

### Install dependencies
```bash
pip install -e ".[dev]"
```

### Run the server
```bash
uvicorn commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`. OpenAPI docs at `/docs`.

### Run tests
```bash
pytest tests/ -v
```

## API Endpoints

### Health
- `GET /health` - Service health check

### SKUs
- `POST /skus` - Create a SKU
- `POST /skus/{sku_id}/adjust-stock` - Adjust stock

### Reservations
- `POST /reservations` - Create a reservation
- `POST /reservations/{reservation_id}/confirm` - Confirm a reservation
- `POST /reservations/{reservation_id}/cancel` - Cancel a reservation

### Orders
- `GET /orders` - List orders (paginated)
- `GET /orders/{order_id}` - Get order details

## Authentication

Mutating endpoints require an `X-API-Key` header. Default key is `test-key-123`.

## Design

- **Models**: Pydantic schemas for validation, SQLAlchemy ORM for persistence
- **Repository**: Data access layer with SQLite backend
- **Service**: Business logic, validation, and state transitions
- **API**: FastAPI endpoints with dependency injection
- **Security**: Simple API key validation
