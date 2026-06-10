# Commerce Service

A production-grade inventory reservation and order orchestration API built with FastAPI and SQLite.

## Overview

This service manages SKU inventory, handles time-limited reservation claims, and orchestrates order creation from confirmed reservations. It enforces stock availability checks, idempotent mutations via idempotency keys, reservation expiration, and strict state transitions.

## Architecture

- **Models**: Domain entities (SKU, Inventory, Reservation, Order)
- **Repository**: SQLite-backed data access with transaction support
- **Service**: Business logic layer enforcing invariants
- **API**: FastAPI endpoints with API-key authentication on mutations
- **Security**: API-key dependency for protected endpoints

## Running

```bash
pip install -e .
pip install -e ".[dev]"

# Start the server
uvicorn src.commerce_service.app:app --reload

# Run tests
pytest
```

## API Endpoints

### Public
- `GET /health` - Health check

### Protected (require `X-API-Key` header)
- `POST /skus` - Create a new SKU
- `POST /skus/{sku_id}/stock` - Adjust inventory level
- `POST /reservations` - Create a reservation
- `POST /reservations/{reservation_id}/confirm` - Confirm a reservation
- `POST /reservations/{reservation_id}/cancel` - Cancel a reservation
- `GET /orders` - List orders (with pagination)

## Example Usage

```bash
# Health check
curl http://localhost:8000/health

# Create a SKU
curl -X POST http://localhost:8000/skus \
  -H "X-API-Key: test-key" \
  -H "Content-Type: application/json" \
  -d '{"sku": "WIDGET-001", "name": "Blue Widget"}'

# Adjust stock
curl -X POST http://localhost:8000/skus/WIDGET-001/stock \
  -H "X-API-Key: test-key" \
  -H "Content-Type: application/json" \
  -d '{"adjustment": 100}'

# Create a reservation
curl -X POST http://localhost:8000/reservations \
  -H "X-API-Key: test-key" \
  -H "Content-Type: application/json" \
  -d '{"sku_id": "WIDGET-001", "quantity": 5, "idempotency_key": "order-123"}'

# Confirm reservation
curl -X POST http://localhost:8000/reservations/1/confirm \
  -H "X-API-Key: test-key"

# Get orders
curl http://localhost:8000/orders \
  -H "X-API-Key: test-key"
```
