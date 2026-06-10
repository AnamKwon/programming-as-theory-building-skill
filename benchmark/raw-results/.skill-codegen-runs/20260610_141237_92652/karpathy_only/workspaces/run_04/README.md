# Commerce Inventory & Order API

A FastAPI-based inventory management and order fulfillment system with stock reservations and idempotency support.

## Features

- **SKU Management**: Create and manage product stock keeping units
- **Stock Adjustment**: Adjust inventory levels with positive/negative amounts
- **Reservations**: Reserve stock with automatic expiration after 300 seconds
- **Idempotency**: Retry-safe operations using idempotency keys
- **Order Management**: Convert confirmed reservations into orders
- **Pagination**: Browse orders with configurable page size

## Installation

```bash
pip install -e ".[dev]"
```

## Running the Server

```bash
uvicorn commerce_service.app:app --reload
```

The server runs on `http://localhost:8000`

## API Endpoints

### Health Check
- `GET /health` - Service health status (no auth required)

### SKU Management
- `POST /skus` - Create a new SKU with initial stock (requires API token)

### Stock Management
- `POST /stock/adjust` - Adjust stock for a SKU (requires API token)

### Reservations
- `POST /reservations` - Create a stock reservation (requires API token)
- `POST /reservations/{id}/confirm` - Confirm a reservation and create an order (requires API token)
- `POST /reservations/{id}/cancel` - Cancel a reservation and restore stock (requires API token)

### Orders
- `GET /orders` - List orders with pagination (no auth required)

## Authentication

Mutating endpoints require an API token via the `X-API-Key` header.

Example:
```bash
curl -X POST http://localhost:8000/skus \
  -H "X-API-Key: test-key-123" \
  -H "Content-Type: application/json" \
  -d '{"sku": "PROD001", "initial_stock": 100}'
```

## Testing

```bash
pytest tests/ -v
```
