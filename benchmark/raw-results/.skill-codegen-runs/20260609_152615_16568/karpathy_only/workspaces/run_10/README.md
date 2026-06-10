# Commerce Service

Inventory reservation and order orchestration API.

## Setup

```bash
pip install -e ".[dev]"
```

## Run

```bash
uvicorn commerce_service.app:app --reload
```

## Test

```bash
pytest
```

## API

- `GET /health` - Health check
- `POST /skus` - Create SKU (requires API key)
- `PATCH /skus/{sku_id}/stock` - Adjust stock (requires API key)
- `POST /reservations` - Create reservation (requires API key)
- `POST /reservations/{reservation_id}/confirm` - Confirm reservation (requires API key)
- `POST /reservations/{reservation_id}/cancel` - Cancel reservation (requires API key)
- `GET /orders` - List orders with pagination (requires API key)
- `GET /orders/{order_id}` - Get order details (requires API key)

## API Key

Pass the API key via the `X-API-Key` header. Default key is `test-key-123`.
