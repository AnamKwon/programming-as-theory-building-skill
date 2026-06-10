# Commerce Service

Inventory reservation and order orchestration API for a small commerce backend.

## Running

```bash
pip install -e .
uvicorn commerce_service.app:app --reload
```

## Testing

```bash
pip install -e ".[dev]"
pytest tests/
```

## API Overview

- `GET /health` - Health check
- `POST /skus` - Create a SKU
- `POST /stock/{sku_id}/adjust` - Adjust stock quantity
- `POST /reservations` - Create a reservation (idempotent)
- `POST /reservations/{reservation_id}/confirm` - Confirm a reservation to an order
- `POST /reservations/{reservation_id}/cancel` - Cancel a reservation
- `GET /orders` - List orders with pagination

All mutating endpoints require the `X-API-Key` header.

## Architecture

- **models.py**: Pydantic schemas and SQLAlchemy ORM models
- **repository.py**: Data access layer with SQLite backend
- **service.py**: Business logic for reservations and orders
- **security.py**: API key validation
- **app.py**: FastAPI application and route definitions
