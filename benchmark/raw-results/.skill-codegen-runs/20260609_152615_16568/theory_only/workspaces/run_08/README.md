# Commerce Service

A FastAPI-based inventory reservation and order orchestration service for small commerce backends.

## Features

- **SKU Management**: Create and track stock for products
- **Stock Adjustment**: Increase or decrease stock quantities
- **Reservations**: Temporarily hold stock with automatic expiration
- **Idempotency**: Retry-safe reservation creation using idempotency keys
- **Order Orchestration**: Confirm reservations into orders with state tracking
- **Pagination**: Retrieve orders with limit/offset
- **API Key Security**: Protect mutating endpoints with API key validation
- **SQLite Persistence**: Lightweight, file-based data store

## Setup

```bash
pip install -e ".[dev]"
```

## Running

```bash
python -m uvicorn commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`. OpenAPI docs at `http://localhost:8000/docs`.

## Testing

```bash
pytest
```

## Architecture

- **Models**: Pydantic request/response schemas and SQLAlchemy ORM models
- **Repository**: Data access abstraction over SQLite
- **Service**: Business logic and validation rules
- **Security**: API key extraction and validation
- **App**: FastAPI endpoints and request routing

## API Key

Set the `API_KEY` environment variable to protect mutating endpoints. Example:

```bash
export API_KEY="test-key-123"
```

Default: `"dev-key"` (development only).

## Endpoints

### Health
- `GET /health`: Service health check

### SKUs
- `POST /skus`: Create a SKU (requires API key)
- `POST /skus/{sku_id}/adjust-stock`: Adjust stock (requires API key)

### Reservations
- `POST /reservations`: Create a reservation (requires API key + idempotency key)
- `POST /reservations/{reservation_id}/confirm`: Confirm reservation (requires API key)
- `DELETE /reservations/{reservation_id}`: Cancel reservation (requires API key)

### Orders
- `GET /orders`: List orders with pagination
