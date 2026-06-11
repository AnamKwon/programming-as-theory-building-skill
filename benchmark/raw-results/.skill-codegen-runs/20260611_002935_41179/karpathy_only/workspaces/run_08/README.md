# Commerce Inventory & Order API

A FastAPI-based inventory and order management system with reservation support.

## Features

- SKU management with stock tracking
- Reservation system with idempotency
- Order confirmation with expiration enforcement
- Pagination support for order retrieval
- API key authentication for mutations

## Installation

```bash
pip install -e .
```

For development and testing:

```bash
pip install -e ".[dev]"
```

## Running the API

```bash
uvicorn commerce_service.app:app --reload
```

The API will be available at http://localhost:8000

Health check endpoint: GET http://localhost:8000/health

## API Endpoints

- **GET /health** - Health check
- **POST /skus** - Create a new SKU with initial stock
- **POST /stock/adjust** - Adjust stock for a SKU
- **POST /reservations** - Create a reservation (requires idempotency key)
- **POST /reservations/{id}/confirm** - Confirm a pending reservation
- **POST /reservations/{id}/cancel** - Cancel a pending reservation
- **GET /orders** - List orders with pagination

## Testing

```bash
pytest tests/
```
