# Commerce Service

A FastAPI-based inventory reservation and order orchestration service for small commerce backends.

## Features

- **SKU Management**: Create SKUs with initial stock levels
- **Stock Adjustment**: Increase or decrease stock for SKUs
- **Reservation System**: Reserve stock with automatic expiration (5 minutes)
- **Idempotency**: Prevents duplicate reservations via idempotency keys
- **Order Fulfillment**: Confirm reservations into orders with state transitions
- **Pagination**: Browse orders with limit/offset pagination
- **API Key Security**: All mutations require API-Key header

## Quick Start

```bash
pip install -e .
pip install -e ".[dev]"

# Run the service
python -m uvicorn commerce_service.app:app --reload

# Run tests
pytest tests/
```

## API Endpoints

### Health
- `GET /health` - Service health check

### SKUs
- `POST /skus` - Create a new SKU (requires API-Key)
- `POST /skus/{sku_id}/adjust-stock` - Adjust stock level (requires API-Key)

### Reservations
- `POST /reservations` - Create a reservation (requires API-Key)
- `POST /reservations/{reservation_id}/confirm` - Confirm a reservation into an order (requires API-Key)
- `POST /reservations/{reservation_id}/cancel` - Cancel a reservation (requires API-Key)

### Orders
- `GET /orders` - List orders with pagination

## Architecture

- **Models** (`models.py`): Pydantic request/response schemas and SQLite ORM models
- **Repository** (`repository.py`): Data access layer with SQLite backend
- **Service** (`service.py`): Business logic and order orchestration rules
- **Security** (`security.py`): API key validation
- **App** (`app.py`): FastAPI application with endpoint definitions

## Database

Uses SQLite with file-based storage at `commerce.db`. Schema is auto-created on startup.

## Business Rules

- **Reservations**: Valid for 5 minutes; expired reservations cannot be confirmed
- **Stock**: Cannot reserve more than available stock
- **Idempotency**: Same idempotency key + SKU returns the same reservation
- **State Transitions**: Reservations → Confirmed Orders or Cancelled
