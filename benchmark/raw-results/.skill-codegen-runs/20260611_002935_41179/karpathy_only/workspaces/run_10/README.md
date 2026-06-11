# Commerce Inventory & Order API

A FastAPI-based REST API for managing inventory, reservations, and orders with transactional consistency.

## Features

- **SKU Management**: Create and manage stock keeping units with inventory levels
- **Stock Adjustment**: Increase or decrease available stock
- **Reservation System**: Reserve stock with idempotency guarantees
- **Reservation Lifecycle**: Confirm, cancel, or expire reservations with automatic stock management
- **Order Management**: Create orders from confirmed reservations with pagination
- **API Key Authentication**: Secure mutating operations with API token validation

## Architecture

- **FastAPI**: High-performance async web framework
- **Pydantic v2**: Request/response validation
- **SQLite**: Lightweight embedded database
- **Repository Pattern**: Clean separation between service and data access layers

## Project Structure

```
.
├── pyproject.toml                 # Project configuration and dependencies
├── README.md                      # This file
├── src/
│   └── commerce_service/
│       ├── __init__.py           # Package initialization
│       ├── app.py                # FastAPI application and endpoints
│       ├── models.py             # Pydantic models for validation
│       ├── repository.py         # Database operations
│       ├── service.py            # Business logic layer
│       └── security.py           # API key validation
└── tests/
    ├── test_service.py           # Service layer unit tests
    └── test_api.py               # API integration tests
```

## Installation

```bash
pip install -e ".[dev]"
```

## API Endpoints

### Health Check
- **GET** `/health` - Health status (no auth required)
  ```json
  {"status": "ok"}
  ```

### SKU Management
- **POST** `/skus` - Create a new SKU (requires API key)
  ```json
  {
    "sku": "SKU-001",
    "initial_stock": 100
  }
  ```

### Stock Adjustment
- **POST** `/stock/adjust` - Adjust stock levels (requires API key)
  ```json
  {
    "sku": "SKU-001",
    "amount": -50
  }
  ```

### Reservations
- **POST** `/reservations` - Create a reservation (requires API key)
  ```json
  {
    "sku": "SKU-001",
    "quantity": 30,
    "idempotency_key": "unique-id"
  }
  ```
  **Returns 400** if insufficient stock

- **POST** `/reservations/{id}/confirm` - Confirm a reservation (requires API key)
  - Changes status from PENDING to CONFIRMED
  - Creates an Order record
  - Returns 400 if reservation is expired (>300 seconds old)
  - Returns 400 if not in PENDING state

- **POST** `/reservations/{id}/cancel` - Cancel a reservation (requires API key)
  - Changes status to CANCELLED
  - Restores reserved stock

### Orders
- **GET** `/orders` - List orders with pagination (no auth required)
  - Query parameters: `page` (default: 1), `size` (default: 10)

## Authentication

All mutating endpoints (POST, PUT, DELETE) require the `X-API-Key` header:

```bash
curl -H "X-API-Key: secret-api-key" \
  -X POST http://localhost:8000/skus \
  -H "Content-Type: application/json" \
  -d '{"sku": "SKU-001", "initial_stock": 100}'
```

Default API key: `secret-api-key`

## Business Rules

### Idempotency
Reservation creation is idempotent. If a request with the same `idempotency_key` is retried, the same reservation is returned without re-deducting stock.

### Expiration
Reservations automatically expire 300 seconds after creation. Attempting to confirm an expired reservation:
1. Changes status to EXPIRED
2. Restores the reserved stock
3. Returns HTTP 400

### Stock Validation
- Creating a reservation requires available stock ≥ quantity
- Insufficient stock returns HTTP 400
- Stock is immediately deducted on successful reservation creation
- Stock is restored on cancellation

## Running the Application

```bash
# Development server
uvicorn src.commerce_service.app:app --reload

# Production server
uvicorn src.commerce_service.app:app --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`.

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/

# Run specific test file
pytest tests/test_api.py

# Run specific test
pytest tests/test_api.py::test_create_sku_authorized
```

## Test Coverage

- **Happy path workflow**: SKU creation → Reservation → Confirmation → Order lookup
- **Insufficient stock rejection**: HTTP 400 when quantity exceeds available stock
- **Idempotent retry**: Duplicate requests return identical results without double-deduction
- **Expired reservation rejection**: Stock restored, status updated to EXPIRED
- **Unauthorized mutation blocking**: Missing/Invalid API key returns HTTP 401
- **Pagination**: Correct offset and limit behavior on GET /orders

## Database Schema

### SKUs Table
```sql
CREATE TABLE skus (
    id INTEGER PRIMARY KEY,
    sku TEXT UNIQUE NOT NULL,
    available_stock INTEGER NOT NULL
)
```

### Reservations Table
```sql
CREATE TABLE reservations (
    id INTEGER PRIMARY KEY,
    sku_id INTEGER NOT NULL,
    sku TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    idempotency_key TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (sku_id) REFERENCES skus(id)
)
```

### Orders Table
```sql
CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    reservation_id INTEGER NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    FOREIGN KEY (reservation_id) REFERENCES reservations(id)
)
```

## Error Handling

- **HTTP 400**: Bad request (invalid input, insufficient stock, invalid state)
- **HTTP 401**: Unauthorized (invalid/missing API key)
- **HTTP 403**: Forbidden (missing API key header)
- **HTTP 404**: Not found (resource doesn't exist)

## Development

### Code Style
- PEP 8 compliant
- Type hints throughout
- Clear separation of concerns

### Key Design Decisions
- **Repository Pattern**: All database operations isolated in `repository.py` for testability
- **Service Layer**: Business logic centralized in `service.py` for reusability
- **In-Memory Default**: SQLite `:memory:` database for testing, file-based for production
- **UTC Timestamps**: All timestamps stored in ISO format UTC

## License

Proprietary - Commerce Service
