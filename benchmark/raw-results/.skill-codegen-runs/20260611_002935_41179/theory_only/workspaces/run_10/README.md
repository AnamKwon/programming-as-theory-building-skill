# Commerce Inventory & Order API

A FastAPI-based inventory management and order processing service with stock reservation, expiration handling, and idempotent operations.

## Installation

```bash
pip install -e ".[dev]"
```

## Running the Service

```bash
uvicorn src.commerce_service.app:app --reload
```

The service will be available at `http://localhost:8000`.

## API Endpoints

- `GET /health` - Health check
- `POST /skus` - Create SKU with initial stock
- `POST /stock/adjust` - Adjust stock level
- `POST /reservations` - Create a stock reservation (idempotent)
- `POST /reservations/{id}/confirm` - Confirm a reservation
- `POST /reservations/{id}/cancel` - Cancel a reservation
- `GET /orders` - Paginated list of orders

## Authentication

All mutating endpoints (POST, PUT, DELETE) require an `Authorization: Bearer <API_TOKEN>` header.

## Testing

```bash
pytest tests/
```
