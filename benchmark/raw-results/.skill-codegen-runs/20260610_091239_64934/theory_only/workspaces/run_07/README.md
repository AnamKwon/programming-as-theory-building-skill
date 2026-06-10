# Commerce Service

A FastAPI-based inventory reservation and order orchestration service.

## Features

- Stock and SKU management
- Reservation creation with expiration
- Reservation confirmation and cancellation
- Order lookup with pagination
- API key authentication for mutations
- Idempotent reservation retry
- SQLite persistence

## Quick Start

Install dependencies:
```bash
pip install -e .
pip install -e ".[dev]"
```

Run the service:
```bash
python -m uvicorn commerce_service.app:app --reload
```

Run tests:
```bash
pytest tests/
```

## API

### Health
- `GET /health` - Service health check

### SKUs
- `POST /skus` - Create a SKU (requires API key)
- `PUT /skus/{sku_id}/stock` - Adjust stock level (requires API key)

### Reservations
- `POST /reservations` - Create a reservation (requires API key)
- `POST /reservations/{reservation_id}/confirm` - Confirm a reservation (requires API key)
- `POST /reservations/{reservation_id}/cancel` - Cancel a reservation (requires API key)

### Orders
- `GET /orders` - List orders with pagination (requires API key)

## Configuration

Set the API key via environment variable:
```bash
export API_KEY=your-secret-key
```

Default database: `commerce.db` (auto-created on startup)
