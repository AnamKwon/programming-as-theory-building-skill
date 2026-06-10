# Commerce Inventory & Order API

A FastAPI-based service for managing product inventory and reservations with automatic order creation.

## Features

- SKU inventory management
- Stock adjustment and tracking
- Reservation system with idempotency
- Automatic expiration of stale reservations
- Order tracking with pagination
- API token authentication for mutations

## Setup

```bash
pip install -e ".[dev]"
```

## Running

```bash
uvicorn commerce_service.app:app --reload
```

## Testing

```bash
pytest tests/ -v
```

## API Overview

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | /health | No | Health check |
| POST | /skus | Yes | Create SKU with initial stock |
| POST | /stock/adjust | Yes | Adjust stock levels |
| POST | /reservations | Yes | Reserve stock |
| POST | /reservations/{id}/confirm | Yes | Confirm reservation |
| POST | /reservations/{id}/cancel | Yes | Cancel reservation |
| GET | /orders | Yes | List orders (paginated) |

## Authentication

All mutating endpoints require an `X-API-Key` header with value `secret-key`.

## Environment

Set `DATABASE_URL` to customize the SQLite database path (default: `:memory:`).
