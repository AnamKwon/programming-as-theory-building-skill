# Commerce Inventory & Order API

A FastAPI-based service for managing inventory, reservations, and orders with stock validation, idempotency, and time-based expiration.

## Features

- SKU and inventory management
- Reservation system with idempotent requests
- Stock validation and automatic adjustment
- Time-based reservation expiration (300 seconds)
- Order creation and pagination
- API token-based authentication for mutations

## Setup

```bash
pip install -e .
```

## Running

```bash
uvicorn src.commerce_service.app:app --reload
```

## Testing

```bash
pytest tests/ -v
```

## API Endpoints

### Health Check
- `GET /health` - Returns service status (no auth required)

### SKU Management
- `POST /skus` - Create a new SKU with initial stock (requires API key)

### Stock Management
- `POST /stock/adjust` - Adjust stock for a SKU by an amount (requires API key)

### Reservations
- `POST /reservations` - Create a reservation (requires API key)
  - Returns 400 if insufficient stock
  - Idempotent via `idempotency_key`
- `POST /reservations/{id}/confirm` - Confirm a PENDING reservation (requires API key)
  - Returns 400 if reservation is expired (>300s old)
  - Creates an order on confirmation
- `POST /reservations/{id}/cancel` - Cancel a PENDING reservation (requires API key)
  - Restores reserved stock

### Orders
- `GET /orders` - List orders with pagination (no auth required)
  - Query params: `page` (default 1), `size` (default 10)

## Authentication

Mutating endpoints (POST, PUT, DELETE) require an API key via the Authorization header:

```
Authorization: Bearer test-api-key
```

## Database

Uses SQLite with three main tables:
- `skus` - Product SKUs and available stock
- `reservations` - Reservation records with status and timestamps
- `orders` - Order records linked to confirmed reservations
