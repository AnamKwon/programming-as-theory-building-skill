# Commerce Service

Inventory reservation and order orchestration API built with FastAPI and SQLite.

## Features

- SKU and stock management
- Reservation lifecycle (create, confirm, cancel, expire)
- Order orchestration with reservation grouping
- Idempotency via idempotency keys
- API-key authentication for mutating endpoints
- Pagination support for order lookups

## Running

Install dependencies:
```bash
pip install -e .
pip install -e ".[dev]"
```

Run the server:
```bash
python -m uvicorn commerce_service.app:app --reload
```

API will be available at `http://localhost:8000` with docs at `/docs`.

## Testing

```bash
pytest tests/
```

## API Overview

- `POST /health` — Service health check
- `POST /skus` — Create a SKU (requires API key)
- `PATCH /stock/{sku_id}` — Adjust stock (requires API key)
- `POST /reservations` — Create a reservation (requires API key)
- `POST /reservations/{id}/confirm` — Confirm a reservation (requires API key)
- `POST /reservations/{id}/cancel` — Cancel a reservation (requires API key)
- `GET /orders` — List orders with pagination

## Configuration

Set `COMMERCE_API_KEY` environment variable for API key authentication (default: `test-key`).
