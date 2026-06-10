# Commerce Service

A production-style inventory reservation and order orchestration API built with FastAPI, Pydantic, and SQLite.

## Features

- **SKU Management**: Create and manage Stock Keeping Units (products)
- **Inventory Tracking**: Track available and reserved stock quantities
- **Reservations**: Create time-limited reservations with idempotency support
- **Orders**: Convert reservations into confirmed orders
- **Stock Validation**: Automatic validation of stock availability
- **Expiration Handling**: Automatic cleanup of expired reservations
- **Pagination**: Efficient order listing with offset-based pagination
- **API Security**: API key validation for all mutating operations

## Quick Start

### Installation

```bash
pip install -e .
```

### Run the Server

```bash
export API_KEY="demo-key-12345"
python -m uvicorn commerce_service.app:app --reload
```

The server will start at `http://localhost:8000`

### Run Tests

```bash
pip install -e ".[dev]"
pytest
```

## API Endpoints

### Health Check
- `GET /health` - Server health status

### SKU Management
- `POST /skus` - Create a new SKU (requires API key)
  ```json
  {
    "sku_code": "SKU001",
    "name": "Product Name"
  }
  ```

### Stock Management
- `POST /stock` - Adjust stock for a SKU (requires API key)
  ```json
  {
    "sku_id": 1,
    "quantity_delta": 100
  }
  ```

### Reservations
- `POST /reservations` - Create a reservation (requires API key)
  ```json
  {
    "sku_id": 1,
    "quantity": 50,
    "idempotency_key": "unique-key-123",
    "ttl_seconds": 3600
  }
  ```
- `POST /reservations/{id}/confirm` - Confirm a reservation and create an order (requires API key)
- `DELETE /reservations/{id}` - Cancel a reservation (requires API key)

### Orders
- `GET /orders` - List orders with pagination
  ```
  ?limit=20&offset=0
  ```
- `GET /orders/{id}` - Get a specific order

## Architecture

### Database Layer
- **Repository Pattern**: All database access is abstracted behind repository classes
- **SQLAlchemy ORM**: Type-safe database operations with SQLAlchemy models
- **SQLite**: Lightweight embedded database (configurable via `DATABASE_URL`)

### Business Logic
- **Service Layer**: `CommerceService` contains all business rules
- **Validation**: Stock availability, reservation expiration, and state transitions
- **Idempotency**: Request deduplication via idempotency keys

### API Layer
- **FastAPI**: Modern async web framework
- **Pydantic**: Request/response validation with clear error messages
- **Security**: API key-based authentication for mutating operations

## Key Design Decisions

### Inventory Tracking
Inventory is split into two quantities:
- `available_quantity`: Stock ready to be reserved
- `reserved_quantity`: Stock that's currently reserved but not yet confirmed

This allows for efficient stock management without complex locking.

### Reservation Expiration
Reservations have a TTL (time-to-live) in seconds. Expired reservations are:
1. Detected when confirming a reservation
2. Cleaned up on-demand via `cleanup_expired_reservations()`

### Idempotency
Multiple requests with the same `idempotency_key` will return the same reservation, preventing accidental duplicates when network retries occur.

## Configuration

Environment variables:
- `DATABASE_URL`: Database connection string (default: `sqlite:///./commerce.db`)
- `API_KEY`: API key for mutating endpoints (default: `demo-key-12345`)

## Testing

Test coverage includes:
- Happy path: SKU creation, stock adjustment, reservation creation, confirmation
- Error cases: Insufficient stock, expired reservations
- Idempotency: Duplicate reservation requests return same reservation
- Authorization: API key validation on protected endpoints
- Pagination: Correct limit/offset behavior for order listing
