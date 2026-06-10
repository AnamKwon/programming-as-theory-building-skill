# Commerce Service

A FastAPI-based inventory reservation and order orchestration service.

## Features

- SKU and stock management
- Reservation lifecycle (create, confirm, cancel)
- Order tracking with pagination
- Idempotent operations via idempotency keys
- API-key authentication for mutations
- SQLite persistence

## Quick Start

```bash
pip install -e ".[dev]"
pytest
uvicorn commerce_service.app:app --reload
```

## API Endpoints

- `GET /health` - Health check
- `POST /skus` - Create SKU
- `POST /stock/adjust` - Adjust stock
- `POST /reservations` - Create reservation
- `POST /reservations/{id}/confirm` - Confirm reservation
- `POST /reservations/{id}/cancel` - Cancel reservation
- `GET /orders` - List orders with pagination
- `GET /orders/{id}` - Get order details

## Authentication

Mutating endpoints require `X-API-Key` header.
