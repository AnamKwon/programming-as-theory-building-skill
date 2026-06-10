# Commerce Inventory & Order API

A FastAPI-based service for managing SKU inventory, stock reservations, and order fulfillment.

## Features

- SKU inventory management with stock tracking
- Reservation system with idempotent request handling
- Order creation from confirmed reservations
- Automatic stock expiration enforcement (300 second window)
- API token-based authentication for mutating operations
- SQLite persistence

## Quick Start

### Installation

```bash
pip install -e .
pip install -e ".[dev]"  # for development and testing
```

### Running the Server

```bash
uvicorn src.commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`.

### Running Tests

```bash
pytest
```

## API Endpoints

### Health Check
- `GET /health` - Server health status (no authentication required)

### SKU Management
- `POST /skus` - Create a new SKU with initial stock (requires API token)
- `POST /stock/adjust` - Adjust stock levels for a SKU (requires API token)

### Reservations
- `POST /reservations` - Create a new reservation (requires API token)
- `POST /reservations/{id}/confirm` - Confirm a pending reservation (requires API token)
- `POST /reservations/{id}/cancel` - Cancel a pending reservation (requires API token)

### Orders
- `GET /orders` - List orders with pagination (requires API token)

## Authentication

All mutating endpoints (POST, PUT, DELETE) require an `X-API-Token` header with a valid API token.

## Database

The service uses SQLite for data persistence. The database is automatically initialized on startup.
