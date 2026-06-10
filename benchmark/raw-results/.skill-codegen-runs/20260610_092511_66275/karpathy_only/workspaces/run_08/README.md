# Commerce Service

Inventory reservation and order orchestration API for small commerce backends.

## Features

- Inventory SKU management with real-time stock tracking
- Reservation system with automatic expiration
- Idempotent operations with idempotency keys
- Order state management (reserved → confirmed → cancelled)
- API-key authentication for mutations
- Pagination for order lookups
- Production-ready error handling

## Installation

```bash
pip install -e .
pip install -e ".[dev]"  # for development
```

## Running

Start the service on `http://localhost:8000`:

```bash
python -m uvicorn commerce_service.app:app --reload
```

Health check:

```bash
curl http://localhost:8000/health
```

## API Overview

### Public Endpoints
- `GET /health` - Health check
- `POST /skus` - Create SKU (requires API key)
- `POST /stock/adjust` - Adjust stock (requires API key)
- `POST /reservations` - Create reservation (requires API key, idempotent)
- `POST /reservations/{id}/confirm` - Confirm reservation (requires API key)
- `POST /reservations/{id}/cancel` - Cancel reservation (requires API key)
- `GET /orders` - List orders with pagination (requires API key)

### Authentication

Pass your API key via the `X-API-Key` header:

```bash
curl -H "X-API-Key: test-key" http://localhost:8000/orders
```

## Testing

```bash
pytest
```

## Architecture

- `app.py` - FastAPI application and route definitions
- `models.py` - Pydantic request/response models and SQLAlchemy ORM models
- `repository.py` - Data access layer with SQLite backend
- `service.py` - Business logic and state management
- `security.py` - API key validation
