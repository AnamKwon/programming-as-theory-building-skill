# Commerce Inventory & Order API

A FastAPI-based inventory and order management service with reservation capabilities.

## Features

- SKU management with stock tracking
- Inventory adjustments
- Reservation system with idempotency keys
- Reservation confirmation with expiration checks (300s)
- Order tracking with pagination
- API token authentication for mutations
- SQLite persistence

## Installation

```bash
pip install -e .
pip install -e ".[dev]"  # for development and tests
```

## Running the API

```bash
uvicorn commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`.

## API Endpoints

### Health Check
- `GET /health` - Returns service status (no authentication required)

### SKUs
- `POST /skus` - Create a new SKU with initial stock

### Inventory
- `POST /stock/adjust` - Adjust stock levels for a SKU

### Reservations
- `POST /reservations` - Create a new reservation
- `POST /reservations/{id}/confirm` - Confirm a pending reservation
- `POST /reservations/{id}/cancel` - Cancel a reservation

### Orders
- `GET /orders` - List orders with pagination

## Authentication

All mutation endpoints require an `X-API-Key` header with a valid API token.

## Testing

```bash
pytest tests/
```

## Architecture

- `models.py` - Pydantic v2 models for request/response validation
- `repository.py` - Data access layer with SQLite
- `service.py` - Business logic layer
- `security.py` - Authentication and authorization
- `app.py` - FastAPI application and route definitions
