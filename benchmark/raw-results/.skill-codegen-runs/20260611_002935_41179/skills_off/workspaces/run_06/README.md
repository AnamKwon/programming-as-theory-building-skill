# Commerce Inventory & Order API

A FastAPI-based service for managing SKU inventory, stock reservations, and orders.

## Features

- SKU inventory management with stock tracking
- Reservation system with automatic stock deduction
- Idempotent reservation requests
- Order confirmation workflow
- Automatic reservation expiration (300 seconds)
- API token authentication for mutations
- Paginated order listing

## API Endpoints

### Health Check
- `GET /health` - Health check endpoint (no authentication required)

### SKU Management
- `POST /skus` - Create a new SKU with initial stock
- `POST /stock/adjust` - Adjust stock level for a SKU

### Reservations
- `POST /reservations` - Create a stock reservation (idempotent)
- `POST /reservations/{id}/confirm` - Confirm a pending reservation
- `POST /reservations/{id}/cancel` - Cancel a reservation and restore stock

### Orders
- `GET /orders` - List orders with pagination

## Authentication

All mutation endpoints (POST, PUT, DELETE) require an API token header:
```
X-API-Token: your-token-here
```

## Development

Install dependencies:
```bash
pip install -e ".[dev]"
```

Run tests:
```bash
pytest
```

Run the server:
```bash
uvicorn commerce_service.app:app --reload
```
