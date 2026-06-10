# Commerce Inventory & Order API

A FastAPI-based service for managing inventory SKUs, stock reservations, and order fulfillment.

## Features

- SKU and stock management
- Reservation system with idempotency
- Automatic expiration handling (300-second window)
- Order tracking with pagination
- API token authentication for mutations

## Quick Start

### Installation

```bash
pip install -e .
pip install -e ".[dev]"
```

### Running the API

```bash
python -m uvicorn commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`.

### Running Tests

```bash
pytest
```

## API Endpoints

### Health Check
- `GET /health` - Health status (no auth required)

### SKU Management
- `POST /skus` - Create a new SKU
- `POST /stock/adjust` - Adjust stock levels

### Reservations
- `POST /reservations` - Create a reservation
- `POST /reservations/{id}/confirm` - Confirm a reservation
- `POST /reservations/{id}/cancel` - Cancel a reservation

### Orders
- `GET /orders` - List orders with pagination

## Authentication

All mutating endpoints require an `X-API-Key` header with the correct API token (default: `test-api-key`).

## Database

Uses SQLite for data persistence. The database file is created automatically on first run.
