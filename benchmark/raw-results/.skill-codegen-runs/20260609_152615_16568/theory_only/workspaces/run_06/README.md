# Commerce Service

A production-grade inventory reservation and order orchestration API for small commerce backends.

## Features

- SKU and stock management
- Reservation system with automatic expiration
- Order confirmation and state tracking
- Idempotent operations via idempotency keys
- API-key authentication for mutations
- Pagination for order lookup
- SQLite persistence
- Comprehensive test coverage

## Quick Start

```bash
pip install -e .
pip install -e ".[dev]"
pytest
uvicorn commerce_service.app:app --reload
```

## API Endpoints

### Health
- `GET /health` - Health check

### SKU Management
- `POST /skus` - Create a new SKU (requires API key)
- `POST /skus/{sku_id}/stock` - Adjust stock level (requires API key)

### Reservations
- `POST /reservations` - Create a reservation (requires API key)
- `POST /reservations/{reservation_id}/confirm` - Confirm a reservation into an order (requires API key)
- `POST /reservations/{reservation_id}/cancel` - Cancel a reservation (requires API key)

### Orders
- `GET /orders` - List orders with pagination

## Design

### Repository Layer
Encapsulates all SQLite access. Handles idempotency via request IDs and manages transaction semantics.

### Service Layer
Enforces business rules:
- Stock availability checks before reservation
- Automatic expiration of old reservations (configurable TTL)
- Order state transitions and validation
- Idempotent operation deduplication

### API Layer
FastAPI routes with Pydantic validation and dependency injection for API-key auth.

## Configuration

Reservation TTL (time-to-live) defaults to 15 minutes. Stock levels cannot go negative.
