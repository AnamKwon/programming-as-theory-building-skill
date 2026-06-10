# Commerce Service

Inventory reservation and order orchestration API.

## Features

- SKU and stock management
- Reservation workflow with idempotency and expiration
- Order orchestration and state transitions
- API key authentication for mutations
- Pagination for order queries
- SQLite backend with repository pattern

## Running

```bash
pip install -e .[dev]
uvicorn commerce_service.app:app --reload
```

Default API key: `test-key-12345` (set `API_KEY` environment variable to override).

## Testing

```bash
pytest -v
```

## API Endpoints

### Health
- `GET /health` — service status

### SKU Management
- `POST /skus` — create SKU (requires API key)
- `POST /skus/{sku_id}/stock/adjust` — adjust stock (requires API key)

### Reservations
- `POST /reservations` — create reservation (requires API key)
- `POST /reservations/{reservation_id}/confirm` — confirm reservation (requires API key)
- `POST /reservations/{reservation_id}/cancel` — cancel reservation (requires API key)

### Orders
- `GET /orders` — list orders with pagination (no auth required)
- `GET /orders/{order_id}` — get order details (no auth required)
