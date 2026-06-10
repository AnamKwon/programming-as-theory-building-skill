# Commerce Service

Inventory reservation and order orchestration API.

## Features

- SKU and stock management
- Reservation system with automatic expiration
- Order lifecycle management
- Idempotency support for mutations
- API key authentication
- Pagination for order queries

## Setup

```bash
pip install -e ".[dev]"
```

## Running

```bash
uvicorn src.commerce_service.app:app --reload
```

Server runs at `http://localhost:8000`.

## API Endpoints

### Health
- `GET /health` - Health check

### SKUs
- `POST /skus` - Create SKU (requires API key)
- `GET /skus/{sku}` - Get SKU details

### Stock
- `POST /skus/{sku}/adjust` - Adjust stock (requires API key)

### Reservations
- `POST /reservations` - Create reservation (requires API key, idempotent)
- `POST /reservations/{reservation_id}/confirm` - Confirm reservation (requires API key)
- `POST /reservations/{reservation_id}/cancel` - Cancel reservation (requires API key)

### Orders
- `GET /orders` - List orders with pagination (requires API key)
- `GET /orders/{order_id}` - Get order details

## Testing

```bash
pytest
pytest -v
```

## API Key

Pass API key via `X-API-Key` header:

```bash
curl -H "X-API-Key: test-key-123" http://localhost:8000/orders
```
