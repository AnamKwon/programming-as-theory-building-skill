# Commerce Service

A FastAPI-based commerce inventory and order management service with idempotent reservations and stock management.

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
pytest tests/
```

## API Documentation

Once running, visit `http://localhost:8000/docs` for interactive API documentation.

## API Endpoints

### Health Check
- `GET /health` - Service health check (no authentication required)

### SKU Management
- `POST /skus` - Create a new SKU with initial stock (requires API key)
- `POST /stock/adjust` - Adjust stock levels for a SKU (requires API key)

### Reservations
- `POST /reservations` - Create a reservation with idempotency support (requires API key)
- `POST /reservations/{id}/confirm` - Confirm a reservation and create an order (requires API key)
- `POST /reservations/{id}/cancel` - Cancel a reservation and restore stock (requires API key)

### Orders
- `GET /orders` - List orders with pagination (no authentication required)

## Authentication

All mutating endpoints (POST, PUT, DELETE) require the `X-API-Key` header with the value `test-api-key`.
