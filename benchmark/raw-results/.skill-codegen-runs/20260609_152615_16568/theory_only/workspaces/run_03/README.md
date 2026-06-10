# Commerce Service

A production-grade inventory reservation and order orchestration API built with FastAPI, Pydantic, and SQLite.

## Features

- **SKU Management**: Create and manage product SKUs
- **Stock Management**: Adjust inventory levels
- **Reservation System**: Reserve stock with idempotency and expiration
- **Order Orchestration**: Track orders with associated reservations
- **Pagination**: Paginated order listing
- **API Key Security**: Protected mutating endpoints with X-API-Key header
- **Service Layer Architecture**: Clean separation of concerns with repository and service layers

## Quick Start

### Installation

```bash
pip install -e .
pip install -e ".[dev]"  # For development and testing
```

### Running the API

```bash
uvicorn commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`.

### Testing

```bash
pytest tests/
```

## API Endpoints

### Health Check

- `GET /health` - Health check (no auth required)

### SKU Management

- `POST /skus` - Create a new SKU (requires API key)
  ```json
  {
    "sku_id": "PROD123",
    "name": "Product Name"
  }
  ```

- `POST /stock/adjust` - Adjust stock level (requires API key)
  ```json
  {
    "sku_id": "PROD123",
    "adjustment": 100
  }
  ```

### Reservations

- `POST /reservations` - Create a reservation (requires API key)
  ```json
  {
    "order_id": "ORD123",
    "sku_id": "PROD123",
    "quantity": 5,
    "idempotency_key": "unique-key-123"
  }
  ```

- `POST /reservations/{reservation_id}/confirm` - Confirm a pending reservation (requires API key)
  ```json
  {}
  ```

- `POST /reservations/{reservation_id}/cancel` - Cancel a reservation (requires API key)
  ```json
  {}
  ```

### Orders

- `GET /orders/{order_id}` - Get order details with reservations
- `GET /orders?offset=0&limit=10` - List orders with pagination

## Authentication

All mutating endpoints (POST methods) require an `X-API-Key` header:

```bash
curl -X POST http://localhost:8000/skus \
  -H "X-API-Key: test-api-key-12345" \
  -H "Content-Type: application/json" \
  -d '{"sku_id": "PROD123", "name": "Product"}'
```

Default API key for testing: `test-api-key-12345`

## Architecture

### Models (`models.py`)
Pydantic request/response schemas for type validation and documentation.

### Repository (`repository.py`)
Data access layer handling all SQLite operations with table creation and queries.

### Service (`service.py`)
Business logic layer implementing:
- Stock availability checks
- Idempotency key validation
- Reservation lifecycle management
- Order state tracking

### Security (`security.py`)
API key validation dependency for FastAPI.

### App (`app.py`)
FastAPI application with endpoint definitions and error handling.

## Database

SQLite database schema includes:
- **skus**: Product definitions
- **stock_levels**: Current inventory (available and reserved)
- **orders**: Order records
- **reservations**: Reservation records with status and expiration

Database file is created as `commerce.db` in the current directory.

## Error Handling

- `400 Bad Request` - Invalid request payload or general errors
- `401 Unauthorized` - Invalid or missing API key
- `404 Not Found` - Resource not found
- `409 Conflict` - Insufficient stock available
- `410 Gone` - Reservation has expired

## Idempotency

The reservation system uses idempotency keys to prevent duplicate reservations:
- Submit the same `idempotency_key` in multiple requests
- Returns the existing reservation instead of creating a new one
- Prevents race conditions and network retry issues

## Reservation Lifecycle

1. **Pending**: Initial state when reservation is created, reserves stock
2. **Confirmed**: Reservation confirmed, stock remains reserved
3. **Cancelled**: Reservation cancelled, stock is released
4. **Expired**: Reservation expired after 15 minutes, stock is released

## Design Principles

- **Separation of Concerns**: Repository, Service, and API layers
- **Repository Pattern**: Database access abstraction
- **Dependency Injection**: FastAPI dependency system for testability
- **Clear Error Messages**: Specific HTTP status codes and error details
- **Production Ready**: In-memory testing, SQLite persistence, proper validation
