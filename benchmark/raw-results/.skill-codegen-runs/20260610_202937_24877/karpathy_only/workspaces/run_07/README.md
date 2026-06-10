# Commerce Inventory & Order API

A FastAPI-based service for managing product SKUs, inventory stock, and order reservations.

## Features

- SKU and stock management
- Reservation system with idempotency keys
- Automatic expiration of old reservations (300 second TTL)
- Order creation from confirmed reservations
- Pagination support for order listing
- API token authentication for mutating operations

## Installation

```bash
pip install -e .
pip install -e ".[dev]"
```

## Running the Server

```bash
python -m uvicorn commerce_service.app:app --reload
```

## API Endpoints

### Public
- `GET /health` - Health check

### SKU Management (requires API token)
- `POST /skus` - Create a SKU with initial stock
- `POST /stock/adjust` - Adjust stock levels

### Reservations (requires API token)
- `POST /reservations` - Create a reservation
- `POST /reservations/{id}/confirm` - Confirm a reservation
- `POST /reservations/{id}/cancel` - Cancel a reservation

### Orders
- `GET /orders` - List orders with pagination

## Testing

```bash
pytest tests/
```
