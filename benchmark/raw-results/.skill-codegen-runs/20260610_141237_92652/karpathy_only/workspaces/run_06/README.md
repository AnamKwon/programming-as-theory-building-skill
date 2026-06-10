# Commerce Inventory & Order API

A FastAPI-based service for managing inventory, reservations, and orders with idempotency and expiration enforcement.

## Installation

```bash
pip install -e .
pip install -e ".[dev]"
```

## Running the Service

```bash
uvicorn src.commerce_service.app:app --reload
```

## Testing

```bash
pytest tests/
```

## API Endpoints

- `GET /health` - Health check (no auth required)
- `POST /skus` - Create a SKU with initial stock
- `POST /stock/adjust` - Adjust stock levels
- `POST /reservations` - Create a reservation with idempotency
- `POST /reservations/{id}/confirm` - Confirm a reservation
- `POST /reservations/{id}/cancel` - Cancel a reservation
- `GET /orders` - List orders with pagination

## Authentication

All mutating endpoints (POST, PUT, DELETE) require an `X-API-Token` header.

Set via environment variable:
```bash
export API_TOKEN=your-secret-token
```
