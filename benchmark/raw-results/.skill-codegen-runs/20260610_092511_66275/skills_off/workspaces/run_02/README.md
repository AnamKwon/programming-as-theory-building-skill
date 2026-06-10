# Commerce Service

A production-grade inventory reservation and order orchestration API built with FastAPI.

## Features

- SKU and stock management
- Reservation creation and confirmation
- Idempotent operations with idempotency keys
- Automatic reservation expiration (default 15 minutes)
- Order state transitions (pending → confirmed → completed)
- API key authentication for mutations
- Paginated order lookup
- SQLite persistence

## Setup

```bash
pip install -e .
pip install -e ".[dev]"
```

## Running

```bash
uvicorn src.commerce_service.app:app --reload
```

The API is available at `http://localhost:8000`.
Health check: `GET /health`

## Testing

```bash
pytest tests/
```

## API Endpoints

- `GET /health` - Health check
- `POST /api/skus` - Create SKU (requires API key)
- `POST /api/inventory/adjust` - Adjust stock (requires API key)
- `POST /api/reservations` - Create reservation (requires API key)
- `POST /api/reservations/{id}/confirm` - Confirm reservation (requires API key)
- `POST /api/reservations/{id}/cancel` - Cancel reservation (requires API key)
- `GET /api/orders` - List orders (paginated)
