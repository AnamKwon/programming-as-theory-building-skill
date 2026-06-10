# Commerce Service

A FastAPI-based inventory reservation and order orchestration API.

## Features

- **SKU Management**: Create and manage product SKUs with inventory tracking
- **Reservation System**: Reserve inventory with expiration and idempotency
- **Order State Machine**: Transition reservations through confirmed and cancelled states
- **API Key Security**: Authenticate mutating endpoints with API keys
- **Pagination**: Browse orders with limit/offset pagination

## Quick Start

```bash
pip install -e ".[dev]"
pytest
uvicorn commerce_service.app:app --reload
```

## API Endpoints

### Health
- `GET /health` - Service health check

### SKUs
- `POST /skus` - Create SKU (requires API key)
- `PATCH /skus/{sku_id}/stock` - Adjust stock level (requires API key)

### Reservations
- `POST /reservations` - Create reservation (requires API key)
- `POST /reservations/{reservation_id}/confirm` - Confirm reservation (requires API key)
- `POST /reservations/{reservation_id}/cancel` - Cancel reservation (requires API key)

### Orders
- `GET /orders` - List orders with pagination

## Architecture

- **models.py**: Pydantic schemas and SQLAlchemy ORM models
- **repository.py**: Data access layer
- **service.py**: Business logic and state transitions
- **app.py**: FastAPI routes and error handling
- **security.py**: API key validation

## Database

SQLite database stored at `commerce.db`. Schema created automatically on first run.
