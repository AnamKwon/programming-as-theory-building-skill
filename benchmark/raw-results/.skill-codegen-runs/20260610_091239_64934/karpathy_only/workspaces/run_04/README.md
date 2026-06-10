# Commerce Service

A production-style inventory reservation and order orchestration API built with FastAPI, Pydantic, and SQLite.

## Features

- **SKU Management**: Create and manage products with stock tracking.
- **Stock Adjustment**: Increase or decrease inventory levels.
- **Order Management**: Create and retrieve orders with full reservation history.
- **Reservation System**: Reserve stock for orders with automatic expiration.
- **Idempotency**: Prevent duplicate reservations using idempotency keys.
- **API Key Security**: Protect mutating endpoints with API key validation.
- **Pagination**: List orders with configurable pagination.
- **State Transitions**: Track reservation and order states (pending, reserved, confirmed, cancelled, expired).

## Quick Start

### Installation

```bash
pip install -e ".[dev]"
```

### Running the Service

```bash
uvicorn src.commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`.

API documentation: `http://localhost:8000/docs`

### Running Tests

```bash
pytest tests/ -v
```

## API Endpoints

### Health Check

- `GET /health` - Service health status (no authentication required)

### SKU Management

- `POST /skus` - Create a new SKU (requires API key)
  ```json
  {
    "sku_code": "PROD001",
    "name": "Product Name",
    "initial_stock": 100
  }
  ```

- `POST /skus/{sku_id}/stock` - Adjust stock level (requires API key)
  ```json
  {
    "quantity": 50
  }
  ```

### Order Management

- `POST /orders` - Create a new order (requires API key)

- `GET /orders/{order_id}` - Retrieve order details

- `GET /orders` - List orders with pagination
  ```
  GET /orders?offset=0&limit=20
  ```

### Reservations

- `POST /orders/{order_id}/reservations` - Create a reservation (requires API key)
  ```json
  {
    "sku_id": 1,
    "quantity": 30,
    "idempotency_key": "unique-key-001"
  }
  ```

- `POST /orders/{order_id}/reservations/{reservation_id}/confirm` - Confirm a reservation (requires API key)

- `POST /orders/{order_id}/reservations/{reservation_id}/cancel` - Cancel a reservation (requires API key)

## Authentication

Mutating endpoints require an `X-API-Key` header. Default valid keys:
- `test-api-key`
- `dev-api-key`

Example:
```bash
curl -X POST http://localhost:8000/orders \
  -H "X-API-Key: test-api-key"
```

## Database

The service uses SQLite for persistence. The database file (`commerce.db`) is created automatically on first run.

### Schema

- **skus**: Product definitions with stock levels
- **orders**: Order records with status tracking
- **reservations**: Stock reservations with expiration tracking

## Business Rules

- **Stock Availability**: Reservations are only allowed if sufficient stock is available.
- **Idempotency**: Multiple reservation requests with the same idempotency key return the same result without duplicating.
- **Reservation Expiration**: Reservations automatically expire after 30 minutes if not confirmed.
- **State Transitions**: 
  - Orders: pending → confirmed/cancelled
  - Reservations: reserved → confirmed/cancelled/expired

## Design Notes

- Service layer handles all business logic and validation.
- Repository layer provides database abstraction.
- Pydantic models validate all request payloads.
- SQLite with row factories for convenient dict-like access.
- Context managers ensure proper connection handling.

## Testing

The test suite includes:

- **Happy path scenarios**: Successful SKU creation, reservation, and confirmation
- **Insufficient stock**: Reservation rejection when stock unavailable
- **Idempotent retry**: Duplicate requests return same result without side effects
- **Expired reservations**: Rejection of confirmation attempts on expired reservations
- **Unauthorized mutations**: API key validation on protected endpoints
- **Pagination**: Order listing with offset and limit parameters

Run all tests:
```bash
pytest tests/ -v
```

Run specific test:
```bash
pytest tests/test_service.py::TestCreateSKU::test_create_sku_success -v
```
