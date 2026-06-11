# Commerce Inventory & Order API

A FastAPI-based inventory and order management system with stock tracking, reservation handling, and order fulfillment workflows.

## Features

- **SKU Management**: Create and manage product stock keeping units
- **Stock Adjustment**: Adjust inventory levels dynamically
- **Reservations**: Reserve stock with idempotency support and automatic expiration
- **Order Fulfillment**: Confirm reservations to create orders
- **Pagination**: List orders with configurable pagination
- **Security**: API token-based authentication for mutations

## Installation

```bash
pip install -e .
pip install -e ".[dev]"
```

## Running the Server

```bash
uvicorn commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`.

## API Endpoints

### Health Check
- `GET /health` - Returns service status (no auth required)

### SKU Management
- `POST /skus` - Create a new SKU with initial stock

### Stock Management
- `POST /stock/adjust` - Adjust stock levels (positive or negative)

### Reservations
- `POST /reservations` - Create a reservation with idempotency
- `POST /reservations/{id}/confirm` - Confirm a pending reservation (max 300s old)
- `POST /reservations/{id}/cancel` - Cancel a reservation

### Orders
- `GET /orders` - List orders with pagination

## Authentication

Mutating endpoints require an `X-API-Key` header. Use any non-empty string as the key for development.

## Testing

```bash
pytest
```

Run with verbose output:
```bash
pytest -v
```
