# Commerce Service

Inventory reservation and order orchestration API for e-commerce fulfillment.

## Features

- **SKU Management:** Create products and adjust stock levels
- **Reservation System:** Reserve stock with automatic expiration (15 minutes)
- **Idempotency:** Retry-safe operations via idempotency keys
- **Order Orchestration:** Confirm reservations into orders, track order state
- **Pagination:** Efficiently query orders with offset/limit
- **API Key Auth:** Protect mutations with X-API-Key header

## Running

```bash
pip install -e ".[dev]"
uvicorn commerce_service.app:app --reload
```

Server runs on `http://localhost:8000`.

## API Endpoints

### Health Check
```
GET /health
```

### SKU Management
```
POST /skus
X-API-Key: your-key
{
  "sku_code": "WIDGET-001",
  "name": "Blue Widget",
  "initial_stock": 100
}

PUT /skus/{sku_id}/stock
X-API-Key: your-key
{
  "quantity_delta": 50
}
```

### Reservations
```
POST /reservations
X-API-Key: your-key
Idempotency-Key: unique-request-id
{
  "sku_id": 1,
  "quantity": 5
}

POST /reservations/{reservation_id}/confirm
X-API-Key: your-key

DELETE /reservations/{reservation_id}
X-API-Key: your-key
```

### Orders
```
GET /orders?offset=0&limit=20
```

## Testing

```bash
pytest tests/ -v
```

Includes tests for:
- Happy path reservation and confirmation
- Insufficient stock error
- Idempotent retry behavior
- Expired reservation rejection
- Unauthorized mutation attempts
- Order pagination
