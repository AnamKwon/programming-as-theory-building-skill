# Commerce Service

A FastAPI-based inventory reservation and order orchestration service.

## Features

- **SKU Management**: Create and manage product SKUs with stock tracking
- **Reservations**: Reserve inventory with automatic expiration and idempotency
- **Orders**: Track orders through lifecycle (reserved → confirmed → completed)
- **API Key Security**: Protect mutating endpoints with API key authentication
- **Pagination**: Browse orders with configurable page sizes

## API Endpoints

- `GET /health` — Health check
- `POST /skus` — Create a SKU
- `POST /stock/adjust` — Adjust SKU stock
- `POST /reservations` — Create a reservation (with idempotency)
- `POST /reservations/{id}/confirm` — Confirm a reservation
- `POST /reservations/{id}/cancel` — Cancel a reservation
- `GET /orders` — List orders with pagination
- `GET /orders/{id}` — Get order details

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
pytest
```

## Authentication

Mutating endpoints (`POST`, `PATCH`) require an `X-API-Key` header. Use any non-empty value for testing (default: configured in app).
