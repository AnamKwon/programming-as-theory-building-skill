# Commerce Service

A FastAPI-based inventory reservation and order orchestration service.

## Quick Start

```bash
pip install -e .
pip install -e ".[dev]"
pytest
uvicorn commerce_service.app:app --reload
```

## API Endpoints

### Public
- `GET /health` - Health check
- `GET /orders` - List orders (with pagination)

### Protected (requires API key)
- `POST /skus` - Create a SKU
- `PATCH /skus/{sku_id}/stock` - Adjust stock for a SKU
- `POST /reservations` - Create a reservation (idempotent via idempotency_key)
- `POST /reservations/{reservation_id}/confirm` - Confirm a reservation
- `POST /reservations/{reservation_id}/cancel` - Cancel a reservation

## Security

Protected endpoints require an `X-API-Key` header. Set via `COMMERCE_API_KEY` environment variable.

## Features

- **Idempotency**: Reservation creation is idempotent via idempotency_key
- **Reservation Expiration**: Reservations expire after 15 minutes
- **Stock Management**: Full validation of availability before reservation
- **Order State Machine**: Reservations → Orders with proper state transitions
- **Pagination**: Order listing supports limit/offset
