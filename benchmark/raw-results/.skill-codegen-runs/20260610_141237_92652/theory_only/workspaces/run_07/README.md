# Commerce Inventory & Order API

A FastAPI-based inventory and order management system with stock reservations, idempotency support, and automatic expiration handling.

## Features

- **SKU Management**: Create and manage stock keeping units
- **Stock Adjustment**: Adjust inventory levels
- **Reservations**: Reserve stock with automatic expiration (300 seconds)
- **Idempotency**: Retry-safe reservation creation using idempotency keys
- **Orders**: Confirm reservations to create orders
- **API Security**: Token-based authentication for mutating endpoints
- **Pagination**: List orders with pagination support

## Installation

```bash
pip install -e ".[dev]"
```

## Running the Server

```bash
uvicorn src.commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`.

## Testing

```bash
pytest tests/
```

## API Endpoints

### Health Check
- `GET /health` - Returns API status

### SKU Management
- `POST /skus` - Create a new SKU with initial stock
- `POST /stock/adjust` - Adjust stock levels

### Reservations
- `POST /reservations` - Create a new reservation
- `POST /reservations/{id}/confirm` - Confirm a pending reservation
- `POST /reservations/{id}/cancel` - Cancel a pending reservation

### Orders
- `GET /orders` - List orders with pagination

## Authentication

All mutating endpoints require an API token passed as the `X-API-Key` header. Default token is `test-key-123`.

## Database

SQLite database is automatically initialized on first run at `commerce.db`.
