# Commerce Inventory & Order API

A FastAPI-based service for managing inventory SKUs, stock levels, and order reservations.

## Features

- SKU management with stock tracking
- Stock adjustment (positive/negative)
- Idempotent reservation system
- Automatic reservation expiration (300 seconds)
- Order confirmation and cancellation
- Paginated order listing
- Static API token authentication for mutations

## Installation

```bash
pip install -e .
pip install -e ".[dev]"
```

## Running the Service

```bash
uvicorn commerce_service.app:app --reload
```

The service will be available at `http://localhost:8000`

Health check: `curl http://localhost:8000/health`

## API Documentation

Interactive API docs available at `http://localhost:8000/docs`

## Testing

```bash
pytest
```

## Authentication

All mutating endpoints (POST, PUT, DELETE) require an `X-API-Key` header with the value `test-api-key`.
