# Commerce Service

A FastAPI-based inventory reservation and order orchestration system for e-commerce backends.

## Features

- **Inventory Management**: SKU creation and stock adjustment
- **Reservations**: Time-limited holds on inventory with idempotency support
- **Order Orchestration**: State transitions from reservation to confirmed order
- **API Key Authentication**: Secured mutating endpoints
- **Pagination**: Efficient order listing with cursor support
- **SQLite Backend**: Self-contained data storage

## Quick Start

### Installation

```bash
pip install -e .
pip install -e ".[dev]"  # For testing
```

### Running the Service

```bash
python -m commerce_service.app
```

The API will be available at `http://localhost:8000`.

### Running Tests

```bash
pytest tests/
```

## API Endpoints

### Health
- `GET /health` - Service health check

### SKUs
- `POST /skus` - Create a new SKU
- `POST /skus/{sku_id}/stock` - Adjust stock level

### Reservations
- `POST /reservations` - Create a reservation (holds inventory)
- `POST /reservations/{reservation_id}/confirm` - Confirm and create order
- `POST /reservations/{reservation_id}/cancel` - Release reservation

### Orders
- `GET /orders` - List orders with pagination
- `GET /orders/{order_id}` - Get order details

## Design

- **Repository Pattern**: Data access is isolated behind a repository interface
- **Service Layer**: Business logic handles stock checks, reservation expiration, and state transitions
- **Idempotency**: Reservation endpoints use idempotency keys for safe retries
- **Expiration**: Reservations auto-expire after 15 minutes
- **SQLite**: Self-contained database with schema auto-creation

## API Key

Set the `X-API-Key` header for mutating endpoints. Default key is `sk-demo-key`.
