# Commerce Service

A production-ready inventory reservation and order orchestration API built with FastAPI, Pydantic, and SQLite.

## Features

- **Health checks** for monitoring service status
- **SKU management** with stock tracking
- **Stock adjustment** with audit trail support
- **Reservation system** with expiration and idempotency
- **Order management** with state transitions
- **API key security** for mutating endpoints
- **Pagination** for order lookups

## Quick Start

### Installation

```bash
pip install -e .
pip install -e ".[dev]"
```

### Running the Server

```bash
python -m uvicorn commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`.

### Running Tests

```bash
pytest
```

## API Endpoints

### Health
- `GET /health` - Service health check

### SKUs
- `POST /skus` - Create a new SKU (requires API key)
- `POST /skus/{sku_id}/stock` - Adjust stock quantity (requires API key)

### Reservations
- `POST /reservations` - Create a reservation (requires API key)
- `POST /reservations/{reservation_id}/confirm` - Confirm a reservation (requires API key)
- `POST /reservations/{reservation_id}/cancel` - Cancel a reservation (requires API key)

### Orders
- `GET /orders` - List orders with pagination (requires API key)

## Architecture

### Models
- **SKU**: Stock-keeping unit with inventory tracking
- **Reservation**: Temporary stock hold with expiration
- **Order**: Collection of confirmed reservations

### Service Layer
Enforces business rules:
- Stock availability validation
- Idempotency key deduplication
- Reservation expiration (30 minutes)
- Order state transitions

### Repository Layer
Abstracts SQLite database access with CRUD operations.

### Security
API key validation via dependency injection on protected endpoints.
