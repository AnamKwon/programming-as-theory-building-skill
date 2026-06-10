# Commerce Inventory & Order API

A FastAPI-based service for managing product inventory, reservations, and orders.

## Features

- SKU inventory management
- Stock adjustment
- Reservation system with idempotency
- Reservation confirmation with expiration enforcement (300 seconds)
- Reservation cancellation with stock restoration
- Order listing with pagination
- API key-based authentication for mutations

## Installation

```bash
pip install -e .
```

## Running the Server

```bash
uvicorn src.commerce_service.app:app --reload
```

## Testing

```bash
pytest tests/
```

## API Endpoints

### Health Check
- `GET /health` - Service health status (no auth required)

### SKU Management
- `POST /skus` - Create a SKU with initial stock
- `POST /stock/adjust` - Adjust stock levels

### Reservations
- `POST /reservations` - Create a reservation
- `POST /reservations/{id}/confirm` - Confirm a reservation
- `POST /reservations/{id}/cancel` - Cancel a reservation

### Orders
- `GET /orders` - List orders with pagination

## Authentication

All mutating endpoints (POST, PUT, DELETE) require an API key via the `X-API-Key` header.
