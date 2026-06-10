# Commerce Service

Inventory reservation and order orchestration API for small commerce backends.

## Features

- **SKU Management**: Create SKUs and manage stock levels
- **Reservations**: Reserve stock with automatic expiration
- **Idempotency**: Replay requests safely using idempotency keys
- **Order Lookup**: Paginated access to confirmed orders
- **Security**: API-key authentication for mutations
- **State Management**: Reservation states (pending, confirmed, cancelled, expired)

## Quick Start

### Install

```bash
pip install -e .
pip install -e ".[dev]"
```

### Run

```bash
uvicorn commerce_service.app:app --reload
```

Server starts at `http://localhost:8000`. API docs at `/docs`.

### Test

```bash
pytest tests/ -v
```

## API Overview

- `GET /health` — Service health check
- `POST /skus` — Create SKU (requires API key)
- `POST /skus/{sku_code}/adjust` — Adjust stock (requires API key)
- `POST /reservations` — Create reservation (requires API key)
- `POST /reservations/{reservation_id}/confirm` — Confirm reservation (requires API key)
- `POST /reservations/{reservation_id}/cancel` — Cancel reservation (requires API key)
- `GET /orders` — List orders with pagination (requires API key)

## Authentication

Pass API key via header: `X-API-Key: your-key-here`

Default key for development: `test-key-123`
