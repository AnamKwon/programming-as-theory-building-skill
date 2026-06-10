# Commerce Service

A production-grade inventory reservation and order orchestration API built with FastAPI and SQLite.

## Features

- **Inventory Management**: Create SKUs and manage stock levels.
- **Reservation System**: Reserve inventory with automatic expiration, confirmation, and cancellation.
- **Idempotency**: Duplicate requests with the same idempotency key return the same result.
- **Order Tracking**: Confirm reservations to create orders and view order history with pagination.
- **API Security**: API-key authentication for mutating endpoints.

## Setup

Install dependencies:

```bash
pip install -e .
pip install -e ".[dev]"  # For development and testing
```

## Running

Start the server:

```bash
uvicorn commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`. View the interactive API docs at `http://localhost:8000/docs`.

## API Endpoints

### Health & Diagnostics

- `GET /health` - Health check endpoint

### SKU Management

- `POST /skus` - Create a new SKU (requires API key)
- `POST /skus/{sku_id}/stock` - Adjust stock for a SKU (requires API key)

### Reservations

- `POST /reservations` - Create a reservation (requires API key)
- `POST /reservations/{reservation_id}/confirm` - Confirm a reservation (requires API key)
- `DELETE /reservations/{reservation_id}` - Cancel a reservation (requires API key)

### Orders

- `GET /orders` - List orders with pagination
- `GET /orders/{order_id}` - Get order details

## Authentication

Include the `X-API-Key` header with a valid API key for all mutating endpoints. The default key is `test-api-key`.

## Testing

Run the test suite:

```bash
pytest
```

## Architecture

- **app.py**: FastAPI application and route handlers
- **models.py**: Pydantic request/response schemas
- **service.py**: Business logic and reservation rules
- **repository.py**: Database access layer
- **security.py**: Authentication and authorization

## Design Notes

- **Reservation Expiry**: Reservations expire 15 minutes after creation. Expired reservations are rejected on confirmation.
- **Idempotency**: Supply an `idempotency_key` in reservation requests to ensure idempotent retries.
- **Order State**: Orders are created when a reservation is confirmed. Order items track the confirmed quantities.
