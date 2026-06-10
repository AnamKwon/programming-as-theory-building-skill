# Commerce Service API

A production-ready inventory reservation and order orchestration API built with FastAPI and SQLite.

## Features

- **SKU Management**: Create and track product inventory
- **Stock Adjustments**: Update stock levels
- **Reservations**: Reserve inventory with automatic expiration
- **Idempotency**: Retry safety via idempotency keys
- **Orders**: Manage order lifecycle from reservation to fulfillment
- **Pagination**: Efficient order listing with cursor-based pagination
- **Security**: API key authentication for mutating endpoints
- **Health Checks**: System readiness monitoring

## Quick Start

### Install

```bash
pip install -e ".[dev]"
```

### Run

```bash
uvicorn src.commerce_service.app:app --reload
```

Server runs on `http://localhost:8000`. API docs at `/docs`.

### Test

```bash
pytest
```

## API Endpoints

### Health
- `GET /health` — System status

### SKUs
- `POST /skus` — Create SKU (requires API key)
- `GET /skus` — List SKUs

### Stock
- `PATCH /skus/{sku_id}/stock` — Adjust stock (requires API key)

### Reservations
- `POST /reservations` — Create reservation (requires API key, idempotent)
- `POST /reservations/{reservation_id}/confirm` — Confirm reservation (requires API key)
- `POST /reservations/{reservation_id}/cancel` — Cancel reservation (requires API key)

### Orders
- `GET /orders` — List orders with pagination

## Architecture

- **Models**: Pydantic schemas and SQLAlchemy ORM models
- **Repository**: Data access abstraction over SQLite
- **Service**: Business logic layer (availability, state transitions, expiration)
- **API**: FastAPI route handlers with dependency injection
- **Security**: API key validation via `Depends()`

## Database

SQLite database auto-creates on first run at `./commerce.db`.

Schemas:
- `skus`: id, name, current_stock
- `reservations`: id, sku_id, quantity, status, expires_at, idempotency_key, created_at
- `orders`: id, reservation_id, status, created_at
