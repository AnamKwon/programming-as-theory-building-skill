# Commerce Service

A production-style inventory reservation and order orchestration API built with FastAPI.

## Features

- **SKU Management**: Create and manage product SKUs
- **Stock Management**: Track and adjust inventory levels
- **Reservations**: Create, confirm, and cancel inventory reservations with expiration
- **Orders**: Persistent order records with state transitions
- **Idempotency**: Prevent duplicate orders using idempotency keys
- **Authentication**: API key authentication for mutating operations
- **Pagination**: Browse orders with offset-based pagination

## Installation

```bash
pip install -e .
pip install -e ".[dev]"  # for development
```

## Running the Service

```bash
python -m uvicorn commerce_service.app:app --host 0.0.0.0 --port 8000
```

## API Endpoints

### Health Check
- `GET /health` - Service health check

### SKUs
- `POST /skus` - Create a SKU (requires API key)

### Stock Management
- `POST /stocks/adjust` - Adjust stock level (requires API key)

### Reservations
- `POST /reservations` - Create a reservation (requires API key)
- `POST /reservations/{reservation_id}/confirm` - Confirm a reservation (requires API key)
- `POST /reservations/{reservation_id}/cancel` - Cancel a reservation (requires API key)

### Orders
- `GET /orders` - List orders with pagination
- `GET /orders/{order_id}` - Get order details

## Testing

```bash
pytest
```

## Architecture

- **app.py**: FastAPI application and route handlers
- **models.py**: Pydantic request/response models and SQLAlchemy ORM models
- **repository.py**: Data access layer with database operations
- **service.py**: Business logic layer with core orchestration rules
- **security.py**: API key authentication dependency
