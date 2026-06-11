# Commerce Inventory & Order API

A FastAPI-based commerce service for managing inventory, reservations, and orders with built-in idempotency, stock validation, and expiration enforcement.

## Features

- SKU and inventory management
- Stock reservation with idempotency guarantees
- Automatic expiration of stale reservations
- Order creation and pagination
- API token authentication on mutating endpoints

## Installation

```bash
pip install -e .
pip install -e ".[dev]"
```

## Running

```bash
uvicorn commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`.

## API Endpoints

### Health Check
- `GET /health` - Health status (no auth required)

### SKU Management
- `POST /skus` - Create a new SKU with initial stock
- `POST /stock/adjust` - Adjust stock level

### Reservations
- `POST /reservations` - Create a reservation with idempotency
- `POST /reservations/{id}/confirm` - Confirm a pending reservation
- `POST /reservations/{id}/cancel` - Cancel a pending reservation

### Orders
- `GET /orders` - List orders with pagination

## Testing

```bash
pytest tests/
```
