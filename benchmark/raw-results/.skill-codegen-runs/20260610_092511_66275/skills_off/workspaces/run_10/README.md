# Commerce Service

A FastAPI-based inventory reservation and order orchestration service.

## Features

- SKU and stock management
- Inventory reservations with expiration
- Order state transitions with idempotency
- API-key authentication for mutations
- Order lookup with pagination

## Quick Start

### Install dependencies

```bash
pip install -e ".[dev]"
```

### Run the service

```bash
uvicorn src.commerce_service.app:app --reload
```

The API is available at `http://localhost:8000`.

### Run tests

```bash
pytest tests/
```

## API Endpoints

- `GET /health` — Health check
- `POST /skus` — Create a SKU
- `POST /skus/{sku_id}/stock` — Adjust stock
- `POST /reservations` — Create a reservation
- `POST /reservations/{reservation_id}/confirm` — Confirm a reservation
- `POST /reservations/{reservation_id}/cancel` — Cancel a reservation
- `GET /orders` — List orders with pagination

## Authentication

Use the `X-API-Key` header for mutations. Set `COMMERCE_API_KEY` environment variable.
