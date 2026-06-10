# Commerce Service API

A FastAPI-based inventory and order management system with stock reservations and expiration handling.

## Features

- SKU management with stock tracking
- Stock adjustment (add/subtract)
- Reservation system with idempotency
- Reservation confirmation with 300-second expiration window
- Order creation and listing with pagination
- API token authentication for mutations

## Setup

Install dependencies:
```bash
pip install -e ".[dev]"
```

## Running

Start the development server:
```bash
uvicorn src.commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`

## API Endpoints

### Health Check
- `GET /health` - Returns `{"status": "ok"}`

### SKU Management
- `POST /skus` - Create a new SKU with initial stock (requires API token)
- `POST /stock/adjust` - Adjust stock level (requires API token)

### Reservations
- `POST /reservations` - Create a reservation (requires API token)
- `POST /reservations/{id}/confirm` - Confirm a reservation and create order (requires API token)
- `POST /reservations/{id}/cancel` - Cancel a reservation and restore stock (requires API token)

### Orders
- `GET /orders` - List orders with pagination

## Authentication

All mutating endpoints (POST, PUT, DELETE) require an `X-API-Key` header with the value `test-secret-token-12345`.

## Testing

Run the test suite:
```bash
pytest
```

Run with coverage:
```bash
pytest --cov=src/commerce_service tests/
```
