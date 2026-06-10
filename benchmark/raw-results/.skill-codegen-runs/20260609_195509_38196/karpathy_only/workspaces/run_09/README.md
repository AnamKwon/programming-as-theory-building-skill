# Commerce Service

A production-grade inventory reservation and order orchestration API built with FastAPI and SQLite.

## Features

- SKU and stock management
- Reservation with expiration and idempotency
- Order confirmation and state transitions
- API key authentication for mutations
- Pagination for order lookup
- Clean repository and service layer architecture

## Quick Start

### Installation

```bash
pip install -e .
pip install -e ".[dev]"
```

### Run the Service

```bash
uvicorn src.commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`.

### Run Tests

```bash
pytest
```

## API Endpoints

### Health Check
- `GET /health` — Service health status

### SKU Management
- `POST /skus` — Create a new SKU (requires API key)
- `PUT /skus/{sku_id}/stock` — Adjust stock level (requires API key)

### Reservations
- `POST /reservations` — Create a reservation (requires API key)
- `POST /reservations/{reservation_id}/confirm` — Confirm a reservation (requires API key)
- `POST /reservations/{reservation_id}/cancel` — Cancel a reservation (requires API key)

### Orders
- `GET /orders` — List orders with pagination (requires API key)

## Architecture

- **Models**: Pydantic schemas and SQLAlchemy ORM models
- **Repository**: Database access layer with context management
- **Service**: Business logic including stock availability, reservation expiration, and order state transitions
- **Security**: API key validation for protected endpoints
- **App**: FastAPI application with endpoint definitions

## Reservation Lifecycle

1. **Creation**: Reserves stock, expires after 1 hour
2. **Confirmation**: Converts to an order, stock becomes permanent
3. **Cancellation**: Releases reserved stock
4. **Expiration**: Auto-released after timeout
