# Commerce Service

A FastAPI-based inventory and order management service with support for stock reservations, order creation, and idempotent operations.

## Installation

```bash
pip install -e .
```

## Development

```bash
pip install -e ".[dev]"
```

## Running the Service

```bash
uvicorn src.commerce_service.app:app --reload
```

## Testing

```bash
pytest
```

## API Endpoints

### Health Check
- `GET /health` - Returns service status (no authentication required)

### SKU Management
- `POST /skus` - Create a new SKU with initial stock
- `POST /stock/adjust` - Adjust stock levels by amount

### Reservations
- `POST /reservations` - Create a stock reservation (idempotent)
- `POST /reservations/{id}/confirm` - Confirm a pending reservation
- `POST /reservations/{id}/cancel` - Cancel a pending reservation

### Orders
- `GET /orders` - Get paginated list of confirmed orders

## Authentication

All mutating endpoints (POST, PUT, DELETE) require an `X-API-Key` header with a valid API token.

## Business Rules

- **Stock Validation**: Reservations require sufficient available stock
- **Idempotency**: Identical reservation requests with same idempotency_key return the same reservation
- **Expiration**: Reservations automatically expire 300 seconds after creation
- **State Management**: Reservations can only be confirmed or cancelled when in PENDING status
