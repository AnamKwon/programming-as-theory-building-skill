# Commerce Service

Inventory reservation and order orchestration API for small commerce backends.

## Features

- SKU management with stock tracking
- Reservation system with idempotency and expiration
- Order creation and state transitions
- API key authentication for mutations
- Pagination support for order queries
- Built with FastAPI, SQLAlchemy, and SQLite

## Setup

```bash
pip install -e ".[dev]"
```

## Running the Service

```bash
python -m uvicorn commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`.

## API Documentation

Once running, visit `http://localhost:8000/docs` for interactive API documentation.

## Testing

```bash
pytest tests/
```

## Architecture

- **models.py**: Pydantic request/response schemas
- **repository.py**: Database access layer (SQLAlchemy)
- **service.py**: Business logic layer
- **security.py**: API key authentication
- **app.py**: FastAPI application and endpoints

## Key Concepts

### Reservations

Reservations hold inventory for a fixed period. They can be in three states:
- **pending**: Created but not yet confirmed
- **confirmed**: Converted to an order, inventory is locked
- **cancelled**: Reservation was cancelled, inventory is released

### Orders

Orders represent confirmed sales. They're created when a reservation is confirmed.

### Idempotency

Create reservation requests include an `idempotency_key`. If the same key is used multiple times, the first reservation is returned and no duplicate is created.

### Stock Management

Each SKU tracks:
- **stock**: Total inventory available
- **reserved**: Inventory held by pending/confirmed reservations
- **available**: stock - reserved
