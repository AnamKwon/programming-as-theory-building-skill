# Commerce Service

A FastAPI-based inventory reservation and order orchestration service for small commerce backends.

## Features

- SKU management with stock tracking
- Reservation creation with expiration and idempotency
- Order lifecycle management (pending → confirmed/cancelled)
- API key authentication for mutations
- Stock availability validation
- Order listing with pagination
- Clean separation: repository (data) → service (logic) → API (endpoints)

## Quick Start

### Install dependencies

```bash
pip install -e ".[dev]"
```

### Run the service

```bash
python -m uvicorn src.commerce_service.app:app --reload
```

Service runs on `http://localhost:8000`

### Run tests

```bash
pytest
```

## API Endpoints

### Public
- `GET /health` - Health check

### Authenticated (require `X-API-Key` header)
- `POST /skus` - Create a SKU
- `POST /skus/{sku_id}/adjust-stock` - Adjust available stock
- `POST /reservations` - Create a reservation
- `POST /reservations/{reservation_id}/confirm` - Confirm a reservation
- `POST /reservations/{reservation_id}/cancel` - Cancel a reservation

### Public (no auth)
- `GET /orders` - List orders (with pagination)
- `GET /orders/{order_id}` - Get order details

## Design

- **Repository**: Raw database access (CRUD operations)
- **Service**: Business logic (stock rules, state transitions, idempotency)
- **API**: HTTP endpoints with validation and error handling
- **Security**: API key extraction and validation

## Configuration

Set the API key via environment variable:

```bash
export COMMERCE_API_KEY=your-secret-key
```

Default key for development: `test-api-key`
