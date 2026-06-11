# Commerce Inventory & Order API

A FastAPI-based service for managing product inventory, stock reservations, and order fulfillment.

## Features

- SKU and inventory management
- Stock adjustment with audit trail
- Reservation system with idempotency
- Order creation and lifecycle management
- Automatic reservation expiration (300 seconds)
- API token-based authentication for mutations
- Pagination support on order listing

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

- `GET /health` - Health check
- `POST /skus` - Create a new SKU with initial stock
- `POST /stock/adjust` - Adjust stock level for a SKU
- `POST /reservations` - Create a stock reservation
- `POST /reservations/{id}/confirm` - Confirm a reservation and create order
- `POST /reservations/{id}/cancel` - Cancel a reservation
- `GET /orders` - List orders with pagination

## Authentication

All mutating endpoints (POST, PUT, DELETE) require an `X-API-Key` header with a valid API token.

## Testing

```bash
pytest tests/ -v
```
