# Commerce Service

A production-grade inventory reservation and order orchestration API built with FastAPI, Pydantic, and SQLite.

## Features

- **SKU Management**: Create and manage stock keeping units
- **Stock Adjustment**: Track and modify inventory levels
- **Reservation System**: Hold inventory with automatic expiration
- **Order Orchestration**: Complete orders from confirmed reservations
- **Idempotency**: Replay-safe operations via idempotency keys
- **API Security**: Key-based authentication for mutations
- **Pagination**: Efficient order lookups with cursor pagination

## Installation

```bash
pip install -e .
pip install -e ".[dev]"  # for development
```

## Running

```bash
python -m uvicorn commerce_service.app:app --reload
```

The API will be available at http://localhost:8000/docs.

## Testing

```bash
pytest
```

## API Endpoints

| Method | Path                              | Description                  |
|--------|-----------------------------------|------------------------------|
| GET    | /health                           | Health check                 |
| POST   | /skus                             | Create SKU                   |
| POST   | /stock/{sku_id}/adjust           | Adjust stock quantity        |
| POST   | /reservations                     | Create reservation           |
| POST   | /reservations/{id}/confirm       | Confirm reservation          |
| POST   | /reservations/{id}/cancel        | Cancel reservation           |
| GET    | /orders                           | List orders (paginated)      |

## Architecture

- **models.py**: Pydantic request/response schemas
- **repository.py**: SQLite data access layer
- **service.py**: Business logic and invariants
- **security.py**: API key validation
- **app.py**: FastAPI application with routes
