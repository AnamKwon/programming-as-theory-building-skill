# Commerce Service

Inventory reservation and order orchestration API for small commerce backends.

## Features

- SKU and stock management
- Inventory reservations with expiration
- Order creation and state transitions
- Idempotent reservation operations
- Paginated order lookup
- API key authentication on mutations

## Running

### Development

```bash
pip install -e ".[dev]"
uvicorn src.commerce_service.app:app --reload
```

### Testing

```bash
pytest tests/
```

## API

### Health Check

```
GET /health
```

### SKU Management

```
POST /skus
X-API-Key: <key>
{
  "sku_code": "SKU-001",
  "name": "Widget",
  "initial_stock": 100
}

POST /skus/{sku_id}/adjust-stock
X-API-Key: <key>
{
  "quantity": 10
}
```

### Reservations

```
POST /reservations
X-API-Key: <key>
{
  "idempotency_key": "req-123",
  "items": [{"sku_id": 1, "quantity": 5}],
  "expiry_minutes": 30
}

POST /reservations/{reservation_id}/confirm
X-API-Key: <key>

POST /reservations/{reservation_id}/cancel
X-API-Key: <key>
```

### Orders

```
GET /orders?skip=0&limit=10

GET /orders/{order_id}
```

## Configuration

Set API key via `COMMERCE_API_KEY` environment variable. Default: `dev-key-123`.
