# Commerce Service

Inventory reservation and order orchestration API built with FastAPI.

## Quick Start

```bash
pip install -e ".[dev]"
pytest
python -m uvicorn src.commerce_service.app:app --reload
```

## API

- `GET /health` - Health check
- `POST /skus` - Create SKU (requires API key)
- `POST /stock/{sku_id}/adjust` - Adjust stock (requires API key)
- `POST /reservations` - Create reservation (requires API key, idempotent)
- `POST /reservations/{reservation_id}/confirm` - Confirm reservation (requires API key)
- `DELETE /reservations/{reservation_id}` - Cancel reservation (requires API key)
- `GET /orders` - List orders (paginated, requires API key)

## Architecture

- **Models**: Pydantic schemas for API payloads, SQLAlchemy ORM for persistence
- **Repository**: Data access layer with transaction boundaries
- **Service**: Business logic for reservations, orders, and stock management
- **Security**: API key validation
- **App**: FastAPI application with dependency injection

## Key Features

- Inventory tracking with stock reservations and confirmations
- Idempotent reservation creation using idempotency keys
- Automatic reservation expiration (15 minutes)
- API key authentication for mutations
- Paginated order listing
- Clear error messages with HTTP status codes
