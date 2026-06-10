# Commerce Inventory & Order API

A FastAPI-based service for managing product inventory, stock reservations, and order fulfillment.

## Features

- **SKU Management**: Create and manage product SKUs with stock levels
- **Stock Adjustment**: Adjust stock levels dynamically
- **Reservations**: Reserve inventory with idempotency guarantees and expiration handling
- **Orders**: Confirm reservations and track orders with pagination
- **Security**: API token-based authentication for all mutations

## API Endpoints

### Health Check
- `GET /health` - Service health status (no authentication required)

### SKU Management
- `POST /skus` - Create a new SKU with initial stock
- `POST /stock/adjust` - Adjust stock levels for a SKU

### Reservations
- `POST /reservations` - Create a reservation with idempotency
- `POST /reservations/{id}/confirm` - Confirm a pending reservation
- `POST /reservations/{id}/cancel` - Cancel a pending reservation

### Orders
- `GET /orders` - List orders with pagination

## Authentication

All mutating endpoints (POST, PUT, DELETE) require an `X-API-Key` header with a valid API token.

## Running the Application

```bash
pip install -e .
pip install -e ".[dev]"
uvicorn commerce_service.app:app --reload
```

## Running Tests

```bash
pytest tests/ -v
```
