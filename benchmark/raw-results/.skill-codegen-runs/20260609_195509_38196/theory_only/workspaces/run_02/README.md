# Commerce Service

A production-grade inventory reservation and order orchestration API built with FastAPI, Pydantic, and SQLite.

## Features

- **SKU Management**: Create and manage product SKUs
- **Stock Control**: Adjust inventory with precise tracking of available and reserved quantities
- **Reservations**: Reserve stock with automatic expiration (24 hours) and idempotency keys
- **Orders**: Confirm reservations to create orders with state management
- **API Key Auth**: Secure mutating endpoints with header-based API key authentication
- **Pagination**: Paginated order listing with configurable limits
- **Clear Errors**: HTTP status codes and messages for all failure scenarios

## Architecture

- **Repository Pattern**: All database access abstracted behind a repository layer
- **Service Layer**: Business logic separated from API endpoints
- **Pydantic Validation**: Request/response validation with clear error messages
- **SQLAlchemy ORM**: Type-safe database models

## Getting Started

### Installation

```bash
pip install -e .
pip install -e ".[dev]"
```

### Running the Server

```bash
python -m commerce_service.app
```

The API will be available at `http://localhost:8000`

API documentation is available at `http://localhost:8000/docs`

### Running Tests

```bash
pytest tests/
```

## API Endpoints

### Health Check
- **GET** `/health` - Returns service health status

### SKU Management
- **POST** `/skus` (requires API key) - Create a new SKU
  ```json
  {"code": "SKU001", "name": "Product A"}
  ```

### Stock Management
- **POST** `/skus/{sku_id}/stock` (requires API key) - Adjust stock quantity
  ```json
  {"quantity": 100}
  ```
- **GET** `/skus/{sku_id}/stock` - Get current stock levels

### Reservations
- **POST** `/reservations` (requires API key) - Create a reservation
  ```json
  {"sku_id": "uuid", "quantity": 50, "idempotency_key": "unique-key"}
  ```
- **POST** `/reservations/{reservation_id}/confirm` (requires API key) - Confirm reservation and create order
- **POST** `/reservations/{reservation_id}/cancel` (requires API key) - Cancel reservation and release stock

### Orders
- **GET** `/orders/{order_id}` - Get order details
- **GET** `/orders?limit=20&offset=0` - List orders with pagination

## Authentication

Include the API key header in all mutating requests:
```
x-api-key: test-api-key-123
```

## Business Logic

### Stock Availability
- Reservations can only be created if available stock (quantity - reserved) meets the request
- Insufficient stock returns HTTP 409

### Idempotency
- Reservation requests with the same `idempotency_key` return the same reservation
- Re-confirming an already confirmed reservation returns the same order

### Reservation Expiration
- Reservations expire 24 hours after creation
- Expired reservations cannot be confirmed and return HTTP 410
- Stock is automatically released when expired reservations are accessed

### Order State
- Orders start in `PENDING` status when a reservation is confirmed
- Cancelling a reservation with a confirmed order marks it `CANCELLED`

## Testing

The test suite covers:
- Happy path flows for all operations
- Insufficient stock scenarios
- Idempotent reservation retry
- Expired reservation rejection
- Unauthorized mutation attempts
- Pagination with various offsets and limits

Run with:
```bash
pytest tests/ -v
```
