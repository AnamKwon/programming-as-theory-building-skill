# Commerce Service

Inventory reservation and order orchestration API for small commerce backends.

## Features

- **Health Checks**: Verify service availability
- **SKU Management**: Create and manage product SKUs
- **Stock Management**: Adjust inventory levels
- **Reservations**: Create, confirm, and cancel reservations with expiration
- **Orders**: Lookup orders with pagination
- **Idempotency**: Prevent duplicate operations using idempotency keys
- **API Security**: API key authentication for mutations

## Quick Start

### Install dependencies

```bash
pip install -e ".[dev]"
```

### Run the service

```bash
python -m uvicorn commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`.

### Run tests

```bash
pytest
```

## API Endpoints

- `GET /health` - Health check
- `POST /api/skus` - Create SKU
- `POST /api/stock/adjust` - Adjust stock for a SKU
- `POST /api/reservations` - Create reservation
- `POST /api/reservations/{id}/confirm` - Confirm reservation
- `POST /api/reservations/{id}/cancel` - Cancel reservation
- `GET /api/orders` - List orders with pagination

## Authentication

Mutating endpoints (`POST`, `PUT`, `DELETE`) require an `X-API-Key` header. Set the API key via environment variable `API_KEY` (default: `test-key`).

## Architecture

- **Models** (`models.py`): Pydantic request/response schemas and SQLAlchemy ORM models
- **Repository** (`repository.py`): Data access layer with database operations
- **Service** (`service.py`): Business logic for reservations, orders, and state transitions
- **Security** (`security.py`): API key verification
- **App** (`app.py`): FastAPI routes and middleware
