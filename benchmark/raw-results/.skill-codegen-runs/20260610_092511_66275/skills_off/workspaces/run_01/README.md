# Commerce Service

A FastAPI-based inventory reservation and order orchestration service with SQLite storage.

## Features

- **Health Checks**: Simple liveness endpoint
- **SKU Management**: Create and manage product inventory
- **Stock Adjustment**: Increase/decrease inventory quantities
- **Reservations**: Reserve inventory with automatic expiration
- **Order Fulfillment**: Confirm reservations into orders
- **Idempotency**: Safe request retry with idempotency keys
- **API Security**: API-key based authentication for mutations
- **Pagination**: List orders with offset/limit pagination

## Quick Start

### Installation

```bash
pip install -e .
```

### Running the Service

```bash
python -m commerce_service.app
# or
uvicorn commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`.

### Running Tests

```bash
pip install -e ".[dev]"
pytest
```

## API Endpoints

### Health
- `GET /health` - Service health check

### SKUs
- `POST /skus` - Create a new SKU (requires API key)
- `POST /skus/{sku_id}/adjust-stock` - Adjust stock quantity (requires API key)

### Reservations
- `POST /reservations` - Create a reservation (requires API key)
- `POST /reservations/{reservation_id}/confirm` - Confirm reservation to order (requires API key)
- `POST /reservations/{reservation_id}/cancel` - Cancel a reservation (requires API key)

### Orders
- `GET /orders` - List orders with pagination (requires API key)
- `GET /orders/{order_id}` - Get order details (requires API key)

## Configuration

Set the API key via environment variable:

```bash
export API_KEY=your-secret-key
```

## Architecture

- **models.py**: Pydantic request/response schemas and SQLAlchemy ORM models
- **repository.py**: Database access layer with transaction support
- **service.py**: Business logic (stock validation, reservation lifecycle, idempotency)
- **security.py**: API key authentication dependency
- **app.py**: FastAPI application and endpoint handlers
