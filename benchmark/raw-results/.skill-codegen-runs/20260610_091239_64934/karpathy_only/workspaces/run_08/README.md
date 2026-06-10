# Commerce Service

A production-ready inventory reservation and order orchestration API built with FastAPI.

## Features

- **SKU Management**: Create and manage product SKUs with stock levels
- **Stock Adjustment**: Increase or decrease inventory for SKUs
- **Reservation System**: Reserve stock with automatic expiration and idempotent retries
- **Order Orchestration**: Confirm reservations into orders with proper state management
- **API Security**: API-key based authentication for mutations
- **Pagination**: Efficient order lookup with limit/offset pagination

## Running

```bash
pip install -e ".[dev]"
uvicorn src.commerce_service.app:app --reload
```

Health check: `GET /health`

## API Key

Set via `X-API-Key` header for mutation endpoints (POST/PUT/DELETE).

## Database

Uses SQLite at `commerce.db` by default. Configure via `DATABASE_URL` environment variable.

## Testing

```bash
pytest
```
