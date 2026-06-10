# Commerce Service

Inventory reservation and order orchestration API for small commerce backends.

## Features

- SKU and stock management
- Reservation system with expiration
- Order confirmation and state tracking
- Idempotent operations via idempotency keys
- API key authentication for mutations
- Paginated order listing
- Production-ready error handling

## Quick Start

### Install

```bash
pip install -e .
```

### Run

```bash
uvicorn commerce_service.app:app --reload
```

Server starts at http://localhost:8000

### Test

```bash
pip install -e ".[dev]"
pytest
```

## API Endpoints

### Health
- `GET /health` — Health check (no auth)

### SKU Management
- `POST /skus` — Create SKU (requires API key)
- `PATCH /stock/{sku_id}` — Adjust stock quantity (requires API key)

### Reservations
- `POST /reservations` — Create reservation (requires API key)
- `POST /reservations/{reservation_id}/confirm` — Confirm reservation to order (requires API key)
- `POST /reservations/{reservation_id}/cancel` — Cancel reservation (requires API key)

### Orders
- `GET /orders` — List orders with pagination (requires API key)
- `GET /orders/{order_id}` — Get order details (requires API key)

## Authentication

Mutating endpoints require an `X-API-Key` header. Default test key: `test-key-123`.

## Database

SQLite database at `./commerce.db`. Created automatically on first run.
