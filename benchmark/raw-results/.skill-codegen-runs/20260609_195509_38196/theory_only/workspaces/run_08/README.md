# Commerce Service

A FastAPI-based inventory reservation and order orchestration system.

## Features

- SKU management with stock tracking
- Reservation system with automatic expiration (15 minutes)
- Idempotent reservation requests via idempotency keys
- Order creation and lookup with pagination
- API key authentication for mutations
- SQLite-backed persistence

## Quick Start

```bash
pip install -e ".[dev]"
pytest
python -m uvicorn commerce_service.app:app --reload
```

The API listens on `http://localhost:8000/docs` for interactive documentation.

## Domain Model

- **SKU:** Stock-keeping unit with available and reserved counts
- **Reservation:** Tentative stock claim that expires after 15 minutes if not confirmed
- **Order:** Confirmed reservation converted to a committed order

## API Endpoints

- `GET /health` — Health check
- `POST /skus` — Create a new SKU (requires API key)
- `POST /skus/{sku_id}/adjust-stock` — Adjust SKU stock (requires API key)
- `POST /reservations` — Create a reservation (requires API key)
- `POST /reservations/{reservation_id}/confirm` — Confirm a pending reservation (requires API key)
- `POST /reservations/{reservation_id}/cancel` — Cancel a reservation (requires API key)
- `GET /orders` — List orders with pagination (requires API key)

## Environment

Set `API_KEY=your-key` (default: `test-key`) to require authentication.
