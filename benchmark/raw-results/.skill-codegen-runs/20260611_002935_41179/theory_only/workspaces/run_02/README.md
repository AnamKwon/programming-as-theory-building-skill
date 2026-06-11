# Commerce Inventory & Order API

A FastAPI-based service for managing product SKUs, stock levels, reservations, and orders with built-in idempotency and expiration handling.

## Features

- **SKU Management**: Create and manage product SKUs with stock levels
- **Stock Adjustment**: Adjust stock levels (positive or negative)
- **Reservations**: Reserve stock with idempotency and expiration checks
- **Orders**: Create orders from confirmed reservations with pagination
- **API Token Authentication**: Secure all mutating operations

## Architecture

- **app.py**: FastAPI application with endpoint definitions
- **models.py**: Pydantic v2 data models
- **service.py**: Business logic layer
- **repository.py**: Database abstraction layer using SQLAlchemy
- **security.py**: Authentication and authorization

## Installation

```bash
pip install -e ".[dev]"
```

## Running

```bash
uvicorn commerce_service.app:app --reload
```

## Testing

```bash
pytest
```

## API Authentication

Include the API token header for all mutating operations:

```
X-API-Key: your-api-token
```

Default test token: `test-token-12345`

## Database

Uses SQLite with automatic schema creation on startup.
