# Commerce Service

Inventory reservation and order orchestration API for small commerce backends.

## Features

- **SKU Management**: Create and manage product stock keeping units
- **Stock Control**: Adjust inventory with signed transactions
- **Reservations**: Hold inventory temporarily with automatic expiration
- **Orders**: Confirm reservations into orders with full lifecycle tracking
- **Idempotency**: Duplicate requests safely handled via idempotency keys
- **Security**: API-key authentication for state-changing operations
- **Pagination**: Efficient order lookup with limit/offset

## Quick Start

### Installation

```bash
pip install -e .
pip install -e ".[dev]"
```

### Running the API

```bash
python -m uvicorn commerce_service.app:app --reload
```

Server starts at `http://localhost:8000`. Swagger UI at `/docs`.

### Running Tests

```bash
pytest -v
```

## API Endpoints

### Health
- `GET /health` - Service status check

### SKUs
- `POST /skus` - Create a SKU (requires API key)
- `GET /skus/{sku_id}` - Retrieve SKU details

### Stock
- `POST /stock/adjust` - Adjust inventory (requires API key)

### Reservations
- `POST /reservations` - Create a reservation (requires API key)
- `POST /reservations/{reservation_id}/confirm` - Confirm to order (requires API key)
- `POST /reservations/{reservation_id}/cancel` - Cancel reservation (requires API key)

### Orders
- `GET /orders` - List orders with pagination

## Authentication

Mutation endpoints (POST/PATCH/DELETE) require an `X-API-Key` header.

Default test key: `test-key-12345`

## Database

Uses SQLite in-memory (or file-based) with automatic schema initialization.

## Design Principles

- **Repository Pattern**: Database access isolated in `repository.py`
- **Service Layer**: Business logic in `service.py` with clear contracts
- **Validation**: Pydantic models enforce schema at boundaries
- **Error Clarity**: HTTP errors include structured detail for debugging
- **Idempotency**: Request deduplication via idempotency key and service-layer logic
