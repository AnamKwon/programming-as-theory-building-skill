# Commerce Service

Inventory reservation and order orchestration API.

## Setup

```bash
pip install -e .
pip install -e ".[dev]"
```

## Run

```bash
python -m commerce_service.app
```

Starts on `http://localhost:8000`. API docs at `/docs`.

## Test

```bash
pytest tests/
```

## API

### Health
- `GET /health` — Service health check.

### SKUs
- `POST /skus` — Create SKU with initial stock (requires API key).
- `POST /skus/{sku_id}/adjust-stock` — Adjust stock quantity (requires API key).

### Reservations
- `POST /reservations` — Create reservation with idempotency key (requires API key).
- `POST /reservations/{res_id}/confirm` — Confirm reservation, convert to order (requires API key).
- `POST /reservations/{res_id}/cancel` — Cancel reservation, release stock (requires API key).

### Orders
- `GET /orders` — Lookup orders with pagination (optional: `?skip=0&limit=10`).

All mutation endpoints require `Authorization: Bearer <api-key>` header. Default key is `test-key` (configurable via `API_KEY` env var).
