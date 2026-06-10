# Commerce Inventory & Order API

A FastAPI-based REST API for managing inventory, reservations, and orders with stock management and idempotency support.

## Features

- **SKU Management**: Create and manage product SKUs with stock levels
- **Stock Adjustment**: Increase or decrease stock for SKUs
- **Reservations**: Reserve stock with automatic deduction and idempotency
- **Orders**: Confirm reservations into orders with expiration checks
- **API Token Authentication**: All mutating operations require API token validation
- **Pagination**: Paginated order listing
- **Database**: SQLite with SQLAlchemy ORM

## Installation

### Prerequisites
- Python 3.9+
- pip

### Setup

```bash
# Install dependencies
pip install -e ".[dev]"

# Run the server
uvicorn src.commerce_service.app:app --reload
```

## API Endpoints

### Health Check
- **GET /health** - Health check endpoint (no auth required)
  ```
  Response: {"status": "ok"}
  ```

### SKU Management
- **POST /skus** - Create a new SKU (requires API token)
  ```json
  Request: {
    "sku": "SKU-001",
    "initial_stock": 100
  }
  Response (201): {
    "id": 1,
    "sku": "SKU-001",
    "available_stock": 100
  }
  ```

- **POST /stock/adjust** - Adjust stock level (requires API token)
  ```json
  Request: {
    "sku": "SKU-001",
    "amount": -10
  }
  Response (200): {
    "sku": "SKU-001",
    "available_stock": 90
  }
  ```

### Reservations
- **POST /reservations** - Create a reservation (requires API token)
  ```json
  Request: {
    "sku": "SKU-001",
    "quantity": 10,
    "idempotency_key": "unique-key-123"
  }
  Response (201): {
    "id": 1,
    "sku": "SKU-001",
    "quantity": 10,
    "status": "PENDING",
    "idempotency_key": "unique-key-123",
    "created_at": "2024-01-01T12:00:00"
  }
  ```

- **POST /reservations/{id}/confirm** - Confirm a reservation (requires API token)
  ```json
  Response (200): {
    "id": 1,
    "reservation_id": 1,
    "sku": "SKU-001",
    "quantity": 10,
    "created_at": "2024-01-01T12:00:00"
  }
  ```

- **POST /reservations/{id}/cancel** - Cancel a reservation (requires API token)
  ```json
  Response (200): {
    "id": 1,
    "sku": "SKU-001",
    "quantity": 10,
    "status": "CANCELLED",
    "idempotency_key": "unique-key-123",
    "created_at": "2024-01-01T12:00:00"
  }
  ```

### Orders
- **GET /orders** - Get paginated orders
  ```
  Query parameters:
  - page (int, default=1): Page number (1-indexed)
  - size (int, default=10): Page size
  
  Response (200): {
    "items": [
      {
        "id": 1,
        "reservation_id": 1,
        "sku": "SKU-001",
        "quantity": 10,
        "created_at": "2024-01-01T12:00:00"
      }
    ],
    "page": 1,
    "size": 10,
    "total": 1
  }
  ```

## Authentication

All mutating endpoints (POST, PUT, DELETE) require an API token via the `X-API-Token` header:

```bash
curl -X POST http://localhost:8000/skus \
  -H "Content-Type: application/json" \
  -H "X-API-Token: test-api-key-12345" \
  -d '{"sku": "SKU-001", "initial_stock": 100}'
```

Default test token: `test-api-key-12345`

## Business Rules

### Stock Validation
- Creating a reservation with insufficient stock returns HTTP 400 with `{"detail": "Insufficient stock"}`

### Idempotency
- Creating a reservation with a duplicate `idempotency_key` returns the existing reservation without mutating stock

### Expiration
- Confirming a reservation created more than 300 seconds ago:
  - Changes status to "EXPIRED"
  - Restores reserved stock
  - Returns HTTP 400 with `{"detail": "Reservation expired"}`

### State Validation
- Confirming or cancelling a reservation not in "PENDING" status returns HTTP 400

## Database Architecture

The application follows a layered architecture:

- **models.py**: SQLAlchemy ORM models and Pydantic schemas
- **repository.py**: Data access layer (SKURepository, ReservationRepository, OrderRepository)
- **service.py**: Business logic layer (CommerceService)
- **app.py**: FastAPI application and endpoint definitions
- **security.py**: API token validation

All database operations are isolated within the repository layer.

## Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src

# Run specific test file
pytest tests/test_api.py

# Run specific test
pytest tests/test_api.py::test_happy_path_workflow
```

## Test Coverage

Tests verify:
- ✅ Happy path workflow (SKU → Reserve → Confirm → Order lookup)
- ✅ Insufficient stock rejection (HTTP 400)
- ✅ Idempotent retry returns matching data without double-deduction
- ✅ Expired reservation rejection and stock restoration
- ✅ Unauthorized mutation block (Missing/Invalid API Key returns HTTP 401)
- ✅ Pagination offset behavior on GET /orders
