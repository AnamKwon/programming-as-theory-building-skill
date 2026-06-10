# Commerce Inventory & Order API

A FastAPI-based service for managing inventory SKUs, stock reservations, and orders with built-in idempotency and expiration handling.

## Features

- **SKU Management**: Create and manage inventory SKUs with stock levels
- **Stock Adjustments**: Increase or decrease stock levels
- **Reservations**: Reserve inventory with idempotency and automatic expiration
- **Orders**: Confirm reservations into orders with pagination support
- **API Security**: Token-based authentication for all mutating endpoints
- **Expiration Handling**: Automatically expire reservations after 300 seconds

## Running the Service

### Installation

```bash
pip install -e ".[dev]"
```

### Starting the Server

```bash
uvicorn src.commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`

### API Documentation

Interactive API docs are available at `http://localhost:8000/docs`

## Testing

```bash
pytest tests/
```

## API Endpoints

### Health Check
- `GET /health` - Health check (no authentication required)

### SKU Management
- `POST /skus` - Create a new SKU (requires API key)
- `POST /stock/adjust` - Adjust stock level (requires API key)

### Reservations
- `POST /reservations` - Create a reservation (requires API key)
- `POST /reservations/{id}/confirm` - Confirm a reservation (requires API key)
- `POST /reservations/{id}/cancel` - Cancel a reservation (requires API key)

### Orders
- `GET /orders` - List orders with pagination (requires API key)

## Authentication

All mutating endpoints (POST, PUT, DELETE) require an `X-API-Key` header with a valid API token.

Default token: `test-key-123`
