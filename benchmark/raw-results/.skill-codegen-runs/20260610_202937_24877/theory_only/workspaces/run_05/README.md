# Commerce Service

A FastAPI-based inventory and order management service with reservation and idempotency support.

## Setup

```bash
pip install -e .
pip install -e ".[dev]"
```

## Running the Service

```bash
python -m uvicorn src.commerce_service.app:app --reload
```

## Testing

```bash
pytest tests/ -v
```

## API Endpoints

- `GET /health` - Health check (no authentication)
- `POST /skus` - Create SKU with initial stock
- `POST /stock/adjust` - Adjust stock levels
- `POST /reservations` - Create a reservation with idempotency support
- `POST /reservations/{id}/confirm` - Confirm a reservation and create an order
- `POST /reservations/{id}/cancel` - Cancel a reservation and restore stock
- `GET /orders` - List orders with pagination

All mutation endpoints (POST, PUT, DELETE) require authentication via `X-API-Key` header.

## Key Features

- **Idempotent Reservations**: Same idempotency_key returns cached result without double-deducting stock
- **Reservation Expiration**: Reservations expire after 300 seconds and cannot be confirmed
- **Stock Management**: Automatic deduction and restoration of stock during reservation lifecycle
- **Pagination**: Ordered list endpoints support page/size parameters
