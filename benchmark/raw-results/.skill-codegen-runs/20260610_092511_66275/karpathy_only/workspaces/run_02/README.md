# Commerce Service

Inventory reservation and order orchestration API for small commerce backends.

## Features

- **SKU Management**: Create and manage product inventory
- **Stock Adjustment**: Modify available stock quantities
- **Reservations**: Temporary holds on inventory with automatic expiration
- **Order Orchestration**: Convert reservations to confirmed orders
- **Idempotency**: Safe retry semantics via idempotency keys
- **Pagination**: Efficient order lookup with pagination
- **API Key Security**: Simple authentication for mutating operations

## Quick Start

```bash
# Install dependencies
pip install -e ".[dev]"

# Run the service
uvicorn commerce_service.app:app --reload

# Run tests
pytest tests/
```

## API Endpoints

### Health
- `GET /health` - Service health check

### SKUs
- `POST /skus` - Create a SKU
- `PATCH /skus/{sku_id}/stock` - Adjust stock quantity

### Reservations
- `POST /reservations` - Create a reservation (requires API key)
- `PATCH /reservations/{reservation_id}/confirm` - Confirm a reservation (requires API key)
- `PATCH /reservations/{reservation_id}/cancel` - Cancel a reservation (requires API key)

### Orders
- `GET /orders` - List orders with pagination

## Authentication

Mutating endpoints require an `X-API-Key` header. Default key is `test-key-123`.

## Architecture

- **Models**: Pydantic schemas and SQLAlchemy ORM models
- **Repository**: Database access abstraction
- **Service**: Business logic and state transitions
- **App**: FastAPI routes and dependencies
- **Security**: API key validation
