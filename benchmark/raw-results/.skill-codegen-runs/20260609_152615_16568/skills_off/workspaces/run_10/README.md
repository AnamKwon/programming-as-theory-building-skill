# Commerce Service

A FastAPI-based inventory reservation and order orchestration system.

## Features

- **SKU Management**: Create SKUs and adjust inventory levels.
- **Reservation System**: Place reservations with stock availability checks.
- **Idempotency**: Idempotency keys prevent duplicate reservations from the same request.
- **Reservation Expiration**: Reservations automatically expire after a configured TTL.
- **Order Orchestration**: Confirm reservations to create orders, with full state tracking.
- **API Key Security**: Mutating endpoints require an API key header.
- **Pagination**: Order lookup supports offset-based pagination.

## API Endpoints

### Health
- `GET /health` - Service health check

### SKUs
- `POST /skus` - Create a new SKU
- `POST /skus/{sku_id}/adjust-stock` - Adjust stock level (requires API key)

### Reservations
- `POST /reservations` - Create a reservation (requires API key)
- `POST /reservations/{reservation_id}/confirm` - Confirm a reservation to order (requires API key)
- `POST /reservations/{reservation_id}/cancel` - Cancel a reservation (requires API key)

### Orders
- `GET /orders` - List orders with pagination
- `GET /orders/{order_id}` - Get a specific order

## Running

```bash
pip install -e ".[dev]"
uvicorn commerce_service.app:app --reload
```

## Testing

```bash
pytest tests/ -v
```

## Architecture

- **models.py**: SQLAlchemy ORM models and Pydantic schemas
- **repository.py**: Data access layer with CRUD operations
- **service.py**: Business logic for reservations and orders
- **security.py**: API key validation
- **app.py**: FastAPI application and endpoints
