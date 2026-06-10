# Commerce Inventory & Order API

A FastAPI-based inventory management and order processing system with stock reservations, idempotency, and expiration enforcement.

## Features

- **Health Check**: Simple status endpoint
- **SKU Management**: Create and manage product SKUs with stock levels
- **Stock Adjustment**: Adjust inventory for SKUs
- **Reservations**: Reserve stock with idempotency guarantees and automatic expiration
- **Order Confirmation**: Convert confirmed reservations into orders
- **Pagination**: Browse orders with configurable page size

## API Endpoints

### Health
- `GET /health` - Returns API status

### SKUs
- `POST /skus` - Create a new SKU with initial stock

### Stock Management
- `POST /stock/adjust` - Adjust stock levels for a SKU

### Reservations
- `POST /reservations` - Reserve stock (with idempotency)
- `POST /reservations/{id}/confirm` - Confirm a reservation (expires after 300 seconds)
- `POST /reservations/{id}/cancel` - Cancel a reservation

### Orders
- `GET /orders` - List orders with pagination

## Authentication

All mutating endpoints require an `X-API-Token` header with the correct token.

## Database

Uses SQLite with SQLAlchemy ORM for schema definition and data persistence.

## Testing

Run tests with:
```bash
pytest tests/ -v
```

## Installation & Running

```bash
pip install -e ".[dev]"
uvicorn src.commerce_service.app:app --reload
```
