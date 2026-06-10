# Commerce Service

An inventory reservation and order orchestration API for small commerce backends.

## Features

- **SKU Management**: Create and manage product SKUs with stock levels
- **Stock Adjustment**: Update inventory levels
- **Reservation System**: Create temporary reservations with automatic expiration
- **Order Confirmation**: Convert reservations into confirmed orders
- **Idempotency**: Duplicate requests are safely deduplicated via idempotency keys
- **API Security**: Endpoint protection via API key authentication
- **Pagination**: Efficient order lookup with cursor-based pagination

## Quick Start

### Installation

```bash
pip install -e .
pip install -e ".[dev]"
```

### Running the Service

```bash
python -m uvicorn commerce_service.app:app --reload
```

The service will be available at `http://localhost:8000`.

### Running Tests

```bash
pytest
```

## API Endpoints

### Health Check
- `GET /health` - Service health status

### SKU Management
- `POST /skus` - Create a new SKU (requires API key)
- Example request:
  ```json
  {
    "sku_code": "WIDGET-001",
    "name": "Blue Widget",
    "description": "A blue widget",
    "stock_level": 100
  }
  ```

### Stock Management
- `POST /stock/adjust` - Adjust stock for a SKU (requires API key)
- Example request:
  ```json
  {
    "sku_id": 1,
    "quantity_change": -5
  }
  ```

### Reservations
- `POST /reservations` - Create a reservation (requires API key)
- Example request:
  ```json
  {
    "order_id": "order-123",
    "sku_id": 1,
    "quantity": 5,
    "idempotency_key": "req-456"
  }
  ```

- `POST /reservations/{id}/confirm` - Confirm a reservation (requires API key)
- `POST /reservations/{id}/cancel` - Cancel a reservation (requires API key)

### Orders
- `GET /orders?limit=20&offset=0` - List orders with pagination

## Architecture

- **Models**: Pydantic request/response schemas and SQLAlchemy ORM models
- **Repository**: Data access layer abstracting SQLite operations
- **Service**: Business logic for reservations, orders, and stock management
- **Security**: API key validation for mutations
- **App**: FastAPI application with route definitions

## Environment Variables

- `API_KEY` - Required API key for mutating endpoints (default: "test-key")
- `DATABASE_URL` - SQLite database path (default: "sqlite:///./commerce.db")
