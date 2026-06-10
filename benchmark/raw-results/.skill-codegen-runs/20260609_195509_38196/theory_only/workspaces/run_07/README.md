# Commerce Service

A production-grade inventory reservation and order orchestration API built with FastAPI and SQLite.

## Design

- **Inventory invariant:** `available + reserved = total` per SKU
- **Reservation:** temporary hold (15-minute expiration) that blocks stock
- **Idempotency:** idempotency keys prevent double-booking from retried requests
- **Order:** confirmed reservation becomes an immutable order record
- **State machines:** reservations (pending → confirmed/expired/cancelled); orders (confirmed → shipped/cancelled)

## Architecture

```
FastAPI routes → Service layer (business logic)
                 ↓
             Repository (database abstraction)
                 ↓
             SQLite (persistence)
```

## Endpoints

- `GET /health` – health check
- `POST /skus` – create SKU (requires API key)
- `POST /skus/{sku}/adjust-stock` – adjust stock level (requires API key)
- `POST /reservations` – create reservation (requires API key)
- `POST /reservations/{reservation_id}/confirm` – confirm reservation (requires API key)
- `POST /reservations/{reservation_id}/cancel` – cancel reservation (requires API key)
- `GET /orders` – list orders with pagination (requires API key)
- `GET /orders/{order_id}` – get order details (requires API key)

## Running

```bash
pip install -e .
pip install -e ".[dev]"
pytest
uvicorn commerce_service.app:app --reload
```

## Testing

```bash
pytest tests/
```

## Configuration

Set `API_KEY` environment variable (default: `dev-key-12345`).
