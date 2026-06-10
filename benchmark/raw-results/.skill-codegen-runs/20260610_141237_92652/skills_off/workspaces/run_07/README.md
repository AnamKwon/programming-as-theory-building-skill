# Commerce Inventory & Order API

A FastAPI-based service for managing SKU inventory, reservations, and orders with built-in idempotency and expiration enforcement.

## Features

- SKU and stock management
- Reservation system with idempotency keys
- Order tracking with pagination
- Reservation expiration (300 seconds)
- API token-based authentication for mutations
- SQLite persistence

## Installation

```bash
pip install -e .
```

## Running

```bash
export API_KEY=your-secret-key
uvicorn commerce_service.app:app --reload
```

## API Endpoints

### Health Check
- `GET /health` - No authentication required

### SKU Management
- `POST /skus` - Create a new SKU with initial stock (requires API key)
- `POST /stock/adjust` - Adjust stock levels (requires API key)

### Reservations
- `POST /reservations` - Create a reservation (requires API key)
- `POST /reservations/{id}/confirm` - Confirm a reservation (requires API key)
- `POST /reservations/{id}/cancel` - Cancel a reservation (requires API key)

### Orders
- `GET /orders` - List orders with pagination

## Testing

```bash
pytest tests/
```
