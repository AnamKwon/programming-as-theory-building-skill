# Commerce Service

A production-style inventory reservation and order orchestration API built with FastAPI, Pydantic, and SQLite.

## Features

- SKU and inventory management
- Reservation creation with idempotency and expiration
- Order confirmation and cancellation workflows
- Stock availability validation
- API-key authentication for mutations
- Pagination support for order lookup
- SQLite persistence

## API Endpoints

### Health & Info
- `GET /health` — Health check

### SKU Management (Requires API Key)
- `POST /skus` — Create a new SKU
- `POST /skus/{sku_id}/stock` — Adjust stock level

### Reservations
- `POST /reservations` — Create a reservation (Requires API Key)
- `POST /reservations/{reservation_id}/confirm` — Confirm a reservation (Requires API Key)
- `POST /reservations/{reservation_id}/cancel` — Cancel a reservation (Requires API Key)

### Orders
- `GET /orders` — List orders with pagination

## Installation

```bash
pip install -e .
pip install -e ".[dev]"
```

## Running

```bash
python -m uvicorn commerce_service.app:app --reload
```

## Testing

```bash
pytest
```
