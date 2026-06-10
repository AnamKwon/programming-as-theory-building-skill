# Commerce Inventory & Order API

A FastAPI-based service for managing inventory, reservations, and orders with ACID guarantees and idempotent operations.

## Features

- **SKU Management**: Create and manage product SKUs with stock tracking
- **Stock Adjustment**: Adjust inventory levels dynamically
- **Reservation System**: Reserve stock with automatic expiration and cancellation
- **Order Fulfillment**: Confirm reservations and create orders
- **Idempotent Operations**: Retry-safe reservation creation via idempotency keys
- **API Security**: Token-based authentication for mutations

## Running the Application

```bash
pip install -e .
pip install -e ".[dev]"
uvicorn src.commerce_service.app:app --reload
```

## Running Tests

```bash
pytest tests/ -v
```

## API Endpoints

- `GET /health` - Health check
- `POST /skus` - Create a SKU
- `POST /stock/adjust` - Adjust stock levels
- `POST /reservations` - Create a reservation
- `POST /reservations/{id}/confirm` - Confirm a reservation
- `POST /reservations/{id}/cancel` - Cancel a reservation
- `GET /orders` - List orders (paginated)

All mutation endpoints require the `X-API-Token` header.
