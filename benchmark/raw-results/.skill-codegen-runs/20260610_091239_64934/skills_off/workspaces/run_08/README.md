# Commerce Service

A production-style inventory reservation and order orchestration API built with FastAPI.

## Quick Start

```bash
pip install -e ".[dev]"
pytest
uvicorn commerce_service.app:app --reload
```

## API Endpoints

- `GET /health` — Health check
- `POST /skus` — Create SKU (requires API key)
- `PATCH /skus/{sku_id}/stock` — Adjust stock (requires API key)
- `POST /reservations` — Create reservation (requires API key)
- `POST /reservations/{reservation_id}/confirm` — Confirm reservation (requires API key)
- `DELETE /reservations/{reservation_id}` — Cancel reservation (requires API key)
- `GET /orders` — List orders with pagination

## Features

- Stock availability checks and reservations with expiration
- Idempotent reservation creation via idempotency keys
- Order state transitions (pending → confirmed or cancelled)
- Repository pattern for data access
- API key authentication for mutations
- Paginated order lookup
- Clear HTTP error responses
