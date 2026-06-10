# Commerce Service

A production-grade inventory reservation and order orchestration API built with FastAPI and SQLite.

## Features

- **Inventory Management**: Create SKUs, adjust stock levels, and track availability
- **Reservation System**: Reserve inventory with automatic expiration, confirmation, and cancellation
- **Order Orchestration**: Create orders from confirmed reservations with state tracking
- **Idempotency**: Guaranteed idempotent operations via idempotency keys
- **API Security**: API-key based authentication for mutating endpoints
- **Pagination**: Efficient order listing with limit/offset pagination

## Getting Started

### Install Dependencies

```bash
pip install -e ".[dev]"
```

### Run the Service

```bash
uvicorn src.commerce_service.app:app --reload
```

Health check: `GET /health`

### Run Tests

```bash
pytest tests/
```

## API Endpoints

### Health Check
- `GET /health` - Service health status

### SKU Management
- `POST /skus` - Create a new SKU (requires API key)
- `POST /skus/{sku_id}/stock` - Adjust stock level (requires API key)

### Reservations
- `POST /reservations` - Create a reservation (requires API key)
- `POST /reservations/{reservation_id}/confirm` - Confirm a reservation (requires API key)
- `POST /reservations/{reservation_id}/cancel` - Cancel a reservation (requires API key)

### Orders
- `GET /orders` - List orders with pagination
- `GET /orders/{order_id}` - Get order details

## Architecture

- **models.py**: Pydantic request/response schemas and domain models
- **repository.py**: SQLAlchemy-based data access layer
- **service.py**: Business logic and state management
- **security.py**: API key validation
- **app.py**: FastAPI application and route handlers

## Database

SQLite database stored at `commerce.db` with schema auto-created on startup.
