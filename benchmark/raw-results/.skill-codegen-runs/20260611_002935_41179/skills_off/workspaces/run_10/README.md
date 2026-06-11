# Commerce Inventory & Order API

A FastAPI-based commerce service for managing inventory, reservations, and orders with idempotent operations and time-based expiration.

## Features

- SKU management with stock tracking
- Reservation system with idempotency
- Order fulfillment with confirmation and cancellation
- Reservation expiration (300 seconds)
- Stock-aware operations
- Pagination support for orders

## API Endpoints

### Health Check
- `GET /health` - Service health check

### SKU Management
- `POST /skus` - Create a new SKU with initial stock

### Stock Operations
- `POST /stock/adjust` - Adjust stock for a SKU

### Reservations
- `POST /reservations` - Create a reservation (requires idempotency key)
- `POST /reservations/{id}/confirm` - Confirm a pending reservation
- `POST /reservations/{id}/cancel` - Cancel a pending reservation

### Orders
- `GET /orders` - List orders with pagination (page, size parameters)

## Authentication

All mutating endpoints (POST, PUT, DELETE) require an `X-API-Key` header with a valid API token.

## Database

Uses SQLite with tables for SKUs, Reservations, and Orders.

## Testing

Run tests with:
```bash
pytest tests/
```
