# Commerce Inventory & Order API

A FastAPI-based service for managing inventory, reservations, and orders with idempotent request handling and expiration validation.

## Installation

```bash
pip install -e ".[dev]"
```

## Running the Server

```bash
uvicorn commerce_service.app:app --reload
```

## API Endpoints

### Health Check
- `GET /health` - Service health status (no authentication)

### SKU Management
- `POST /skus` - Create a new SKU with initial stock
- `POST /stock/adjust` - Adjust stock levels

### Reservations
- `POST /reservations` - Create a reservation (idempotent)
- `POST /reservations/{id}/confirm` - Confirm a reservation and create an order
- `POST /reservations/{id}/cancel` - Cancel a reservation and restore stock

### Orders
- `GET /orders` - List orders with pagination

## Authentication

All mutating endpoints require an API token via the `X-API-Key` header:
```bash
curl -H "X-API-Key: test-key-123" http://localhost:8000/skus
```

## Testing

```bash
pytest
```
