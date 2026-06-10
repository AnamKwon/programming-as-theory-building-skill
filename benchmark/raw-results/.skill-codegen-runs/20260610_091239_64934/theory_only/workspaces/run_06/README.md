# Commerce Service

A FastAPI-based inventory reservation and order orchestration service for small commerce backends.

## Features

- **SKU Management**: Create and manage product SKUs with stock levels
- **Stock Adjustment**: Increase or decrease available inventory
- **Reservations**: Temporary holds on stock with automatic expiration
- **Orders**: Finalized records of confirmed transactions
- **Idempotency**: Duplicate requests with same key return cached results
- **API Key Authentication**: Protect mutating endpoints with header-based API key

## Architecture

- **API Layer** (`app.py`): HTTP endpoints and request validation
- **Service Layer** (`service.py`): Business logic and invariants
- **Repository Layer** (`repository.py`): Data access with SQLite backend
- **Models** (`models.py`): Pydantic schemas and SQLAlchemy ORM entities

## Running

```bash
pip install -e ".[dev]"
uvicorn src.commerce_service.app:app --reload
```

## Testing

```bash
pytest tests/ -v
```

## API Endpoints

- `GET /health` - Health check
- `POST /skus` - Create a SKU (requires API key)
- `POST /stock/adjust` - Adjust inventory level (requires API key)
- `POST /reservations` - Create a reservation (requires API key)
- `POST /reservations/{reservation_id}/confirm` - Confirm reservation (requires API key)
- `POST /reservations/{reservation_id}/cancel` - Cancel reservation (requires API key)
- `GET /orders` - List orders with pagination (requires API key)
- `GET /orders/{order_id}` - Get order details (requires API key)

## Configuration

Set the API key via the `X-API-Key` header on mutating requests. Default key is `test-key` for development.
