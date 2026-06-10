# Commerce Service

Inventory reservation and order orchestration API for small commerce backends.

## Features

- **SKU Management**: Create SKUs and adjust stock levels
- **Reservation System**: Reserve inventory with expiration and idempotency
- **Order Orchestration**: Confirm or cancel reservations, lookup orders with pagination
- **API Security**: Key-based authentication for mutations
- **Production Ready**: Clear error handling, input validation, and test coverage

## Quick Start

### Install

```bash
pip install -e .
```

### Run

```bash
uvicorn commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`. Swagger docs at `/docs`.

### Test

```bash
pytest
```

## Architecture

- **models.py**: Request/response schemas and database models
- **repository.py**: Data access layer (SQLite)
- **service.py**: Business logic and domain rules
- **security.py**: API key validation
- **app.py**: FastAPI application with endpoints

## API Endpoints

All mutation endpoints require `X-API-Key` header.

- `GET /health` - Health check
- `POST /skus` - Create SKU
- `POST /skus/{sku}/stock` - Adjust stock
- `POST /reservations` - Create reservation (idempotent)
- `POST /reservations/{reservation_id}/confirm` - Confirm reservation
- `POST /reservations/{reservation_id}/cancel` - Cancel reservation
- `GET /orders` - List orders with pagination

## Environment

Set `API_KEY` environment variable for authentication (default: "dev-key").
