# Commerce Inventory & Order API

A FastAPI-based inventory and order management system with idempotent reservations and stock tracking.

## Features

- SKU management with stock tracking
- Stock adjustment (positive/negative)
- Idempotent reservation system with expiration checks
- Reservation confirmation with automatic order creation
- Reservation cancellation with stock restoration
- Paginated order listing
- API token-based authentication for mutations

## Installation

```bash
pip install -e ".[dev]"
```

## Running the API

```bash
uvicorn src.commerce_service.app:app --reload
```

## Running Tests

```bash
pytest tests/ -v
```

## API Documentation

Once running, visit `http://localhost:8000/docs` for interactive API documentation.

## Authentication

All mutating endpoints (POST, PUT, DELETE) require an `Authorization` header with a Bearer token.

Default test token: `test-api-key`

## Database

The API uses SQLite for persistence. Database file is created automatically on first run.
