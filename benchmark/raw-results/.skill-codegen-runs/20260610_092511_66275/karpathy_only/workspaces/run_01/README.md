# Commerce Service

A FastAPI-based inventory reservation and order orchestration service for commerce backends.

## Features

- **SKU Management**: Create and manage products with pricing
- **Stock Management**: Track available and reserved inventory
- **Reservations**: Create, confirm, and cancel stock reservations with idempotency and expiration
- **Orders**: Orchestrate multi-item orders with state transitions
- **API Key Security**: Protect mutating endpoints with API key authentication
- **Pagination**: Paginated order lookups
- **Production Ready**: Clean layered architecture, comprehensive tests, error handling

## Quick Start

### Installation

```bash
pip install -e ".[dev]"
```

### Running the Service

```bash
uvicorn commerce_service.app:app --reload
```

The service will start at http://localhost:8000

### Health Check

```bash
curl http://localhost:8000/health
```

## API Endpoints

### Health
- `GET /health` - Health check

### SKU Management
- `POST /skus` - Create a SKU (requires API key)
- Request: `{"name": "Widget", "price": 29.99}`

### Stock Management
- `POST /stock/adjust` - Adjust stock (requires API key)
- Request: `{"sku_id": "sku_123", "quantity_change": 10}`

### Reservations
- `POST /reservations` - Create a reservation (requires API key)
- Request: `{"sku_id": "sku_123", "quantity": 5, "idempotency_key": "unique_key_123"}`
- `POST /reservations/{id}/confirm` - Confirm reservation (requires API key)
- `POST /reservations/{id}/cancel` - Cancel reservation (requires API key)

### Orders
- `GET /orders` - List orders with pagination
- Query params: `skip=0&limit=10`
- `GET /orders/{id}` - Get order details

## Authentication

Include the `X-API-Key` header for mutating endpoints:

```bash
curl -X POST http://localhost:8000/skus \
  -H "X-API-Key: test-key-123" \
  -H "Content-Type: application/json" \
  -d '{"name": "Widget", "price": 29.99}'
```

## Testing

Run the test suite:

```bash
pytest tests/
```

With coverage:

```bash
pytest tests/ --cov=commerce_service
```

## Architecture

- **models.py**: Pydantic request/response models and SQLAlchemy ORM models
- **repository.py**: Data access layer with stock and reservation operations
- **service.py**: Business logic including validation, idempotency, and state transitions
- **security.py**: API key validation
- **app.py**: FastAPI application and route definitions

## Database

SQLite database is created automatically at `commerce.db`. Includes tables for SKUs, stock, reservations, and orders.
