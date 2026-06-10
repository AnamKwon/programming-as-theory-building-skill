# Commerce Inventory & Order API

A FastAPI-based inventory management and order reservation system with stock tracking, idempotent reservations, and order management.

## Features

- **Inventory Management**: Create SKUs and adjust stock levels
- **Reservation System**: Reserve inventory with idempotency support
- **Order Management**: Confirm reservations to create orders
- **Stock Validation**: Prevent overselling
- **Expiration Handling**: Automatically expire old reservations (300s TTL)
- **Pagination**: Browse orders with offset/limit pagination
- **Authentication**: API token-based access control for mutations

## Installation

```bash
pip install -e ".[dev]"
```

## Running the API

```bash
uvicorn commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`

## Running Tests

```bash
pytest tests/ -v
```

## API Endpoints

### Health Check
- `GET /health` - System health check (no authentication required)

### SKU Management
- `POST /skus` - Create a new SKU with initial stock
- `POST /stock/adjust` - Adjust stock for a SKU

### Reservations
- `POST /reservations` - Create a new reservation
- `POST /reservations/{id}/confirm` - Confirm a pending reservation
- `POST /reservations/{id}/cancel` - Cancel a pending reservation

### Orders
- `GET /orders` - List orders with pagination

## Authentication

Mutating endpoints require an API token via the `X-API-Key` header:

```bash
curl -X POST http://localhost:8000/skus \
  -H "X-API-Key: test-token" \
  -H "Content-Type: application/json" \
  -d '{"sku": "ABC123", "initial_stock": 100}'
```

## Database

SQLite database stored at `./commerce.db` containing:
- `skus` - Product SKUs and stock levels
- `reservations` - Reservation records with idempotency keys
- `orders` - Confirmed order records
