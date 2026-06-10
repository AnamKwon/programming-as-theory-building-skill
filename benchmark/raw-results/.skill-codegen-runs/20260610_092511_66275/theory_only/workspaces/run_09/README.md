# Commerce Service

Inventory reservation and order orchestration API built with FastAPI and SQLite.

## Features

- **SKU Management**: Create and manage product stock levels
- **Reservation System**: Reserve inventory with automatic expiration (15 minutes)
- **Idempotency**: Retry-safe reservation requests with idempotency keys
- **Order Orchestration**: Confirm reservations into orders with state transitions
- **Stock Safety**: Atomic operations prevent oversell and race conditions
- **Pagination**: Efficient order lookup with limit/offset
- **API Security**: Key-based authentication for mutation endpoints

## Architecture

```
app.py          → FastAPI routes and HTTP contracts
service.py      → Business logic and reservation rules
repository.py   → SQLite data access layer
models.py       → Pydantic validation schemas
security.py     → API key validation
```

## Quick Start

Install:
```bash
pip install -e ".[dev]"
```

Run:
```bash
python -m commerce_service.app
```

Test:
```bash
pytest tests/
```

## API Endpoints

- `GET /health` - Health check
- `POST /skus` - Create SKU (requires API key)
- `POST /skus/{sku_id}/adjust-stock` - Adjust stock (requires API key)
- `POST /reservations` - Create reservation (requires API key)
- `POST /reservations/{reservation_id}/confirm` - Confirm reservation (requires API key)
- `POST /reservations/{reservation_id}/cancel` - Cancel reservation (requires API key)
- `GET /orders` - List orders with pagination

## Configuration

Set `COMMERCE_API_KEY` environment variable to enable mutations. Default: `dev-key`.

## Reservation Flow

1. Create reservation → pending state (15 min TTL)
2. Confirm reservation → reserved state (moves to order)
3. Cancel reservation → cancelled state (refunds stock)
