# Commerce Inventory & Order API

A FastAPI-based microservice for managing inventory SKUs, stock reservations, and orders with idempotency and expiration enforcement.

## Features

- **SKU Management**: Create and manage stock items with inventory tracking
- **Stock Adjustments**: Increase or decrease stock levels
- **Reservations**: Reserve stock with idempotency guarantees and automatic expiration
- **Orders**: Confirm reservations and create corresponding order records
- **API Token Authentication**: Secure all mutating operations with static token validation
- **Pagination**: List orders with configurable page size

## Installation

```bash
pip install -e ".[dev]"
```

## Running the Server

```bash
uvicorn src.commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`.

## API Endpoints

### Health Check
- `GET /health` - Returns `{"status": "ok"}`

### SKU Management
- `POST /skus` - Create a new SKU with initial stock
  - Input: `{"sku": "string", "initial_stock": int}`
  - Returns: 201 Created

- `POST /stock/adjust` - Adjust stock levels
  - Input: `{"sku": "string", "amount": int}`
  - Returns: 200 OK with updated stock

### Reservations
- `POST /reservations` - Reserve stock
  - Input: `{"sku": "string", "quantity": int, "idempotency_key": "string"}`
  - Returns: 201 Created
  - Enforces: Idempotency, stock availability check

- `POST /reservations/{id}/confirm` - Confirm a reservation
  - Returns: 200 OK
  - Enforces: Expiration check (300s), status validation

- `POST /reservations/{id}/cancel` - Cancel a reservation
  - Returns: 200 OK
  - Restores reserved stock

### Orders
- `GET /orders` - List orders with pagination
  - Query params: `page` (default 1), `size` (default 10)
  - Returns: 200 OK with paginated order list

## Authentication

All mutating endpoints (POST, PUT, DELETE) require an `X-API-Key` header with a valid API token.

Default API key for testing: `test-api-key`

## Running Tests

```bash
pytest tests/ -v
```

## Database

Uses SQLite for persistence. Database file: `commerce.db`

## Architecture

- `app.py` - FastAPI application and route definitions
- `models.py` - Pydantic request/response models and SQLAlchemy ORM models
- `repository.py` - Data access layer
- `service.py` - Business logic
- `security.py` - Authentication dependencies
