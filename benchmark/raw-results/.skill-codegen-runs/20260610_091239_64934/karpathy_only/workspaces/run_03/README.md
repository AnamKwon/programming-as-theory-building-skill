# Commerce Service

Inventory reservation and order orchestration API for small commerce backends.

## API

### Public Endpoints

- `GET /health` — Health check (no auth required)
- `GET /orders` — List orders with pagination (requires API key)

### SKU Management (requires API key)

- `POST /skus` — Create a SKU
- `POST /skus/{sku_id}/adjust-stock` — Adjust stock quantity

### Reservations (requires API key)

- `POST /reservations` — Create a reservation with idempotency
- `POST /reservations/{reservation_id}/confirm` — Confirm a reservation
- `POST /reservations/{reservation_id}/cancel` — Cancel a reservation

## Running

```bash
pip install -e ".[dev]"
pytest tests/
uvicorn commerce_service.app:app --reload
```

## Design Notes

- Reservations expire after 24 hours if not confirmed.
- Idempotency keys prevent duplicate reservations within 24 hours.
- Stock is reserved at creation time; confirmation does not change inventory.
- Orders aggregate multiple reservations into a single transaction unit.
