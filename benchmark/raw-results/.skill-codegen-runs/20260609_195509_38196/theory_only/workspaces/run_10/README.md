# Commerce Service

Inventory reservation and order orchestration API for small commerce backends.

## Overview

A FastAPI-based service that manages product inventory, coordinates reservations, and handles order state transitions. Designed for reliability with idempotency keys, reservation expiration, and clear order tracking.

## Features

- **SKU Management**: Create products and track inventory
- **Stock Adjustment**: Add or remove stock from inventory
- **Reservations**: Reserve inventory with automatic expiration
- **Orders**: Coordinate reservations into orders with full lifecycle management
- **Idempotency**: Safe retry semantics via idempotency keys
- **Authorization**: API key protection for mutations
- **Pagination**: Efficient order lookup with offset/limit

## Architecture

- **API Layer** (app.py): Request/response handling, validation, authentication
- **Service Layer** (service.py): Business rules and state transitions
- **Repository Layer** (repository.py): SQLite data access with schema management
- **Models** (models.py): Pydantic request/response schemas
- **Security** (security.py): API key dependency injection

## Getting Started

### Install

```bash
pip install -e ".[dev]"
```

### Run

```bash
uvicorn commerce_service.app:app --reload
```

Server runs on `http://localhost:8000`

### Test

```bash
pytest -v
```

## API Endpoints

### Health
- `GET /health` — Service readiness check

### SKU Management
- `POST /api/skus` — Create a SKU (requires API key)
- `GET /api/skus/{sku_id}` — Get SKU details

### Stock
- `POST /api/stock/{sku_id}/adjust` — Adjust stock level (requires API key)

### Reservations
- `POST /api/reservations` — Create a reservation (requires API key)
- `POST /api/reservations/{reservation_id}/confirm` — Confirm a reservation (requires API key)
- `POST /api/reservations/{reservation_id}/cancel` — Cancel a reservation (requires API key)

### Orders
- `GET /api/orders` — List orders with pagination

## Environment

Set `API_KEY` environment variable for mutation authorization. Defaults to `test-key` in development.

## Design Notes

- Reservations expire after 15 minutes by default
- Order state: reserved → confirmed → completed (or cancelled)
- All mutations require API key in `X-API-Key` header
- Reads are open (no auth required)
- SQLite database auto-initializes on first run
