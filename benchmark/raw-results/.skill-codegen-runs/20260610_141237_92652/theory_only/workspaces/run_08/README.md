# Commerce Inventory & Order API

A FastAPI-based service for managing inventory SKUs, stock levels, reservations, and orders.

## Features

- SKU and stock management
- Reservation system with idempotency
- Order creation and tracking
- Pagination support
- API token authentication
- Expiration handling for time-sensitive reservations

## Setup

### Install dependencies

```bash
pip install -e ".[dev]"
```

### Run the server

```bash
python -m uvicorn src.commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`.

### Run tests

```bash
pytest
```

## API Endpoints

### Health Check
- `GET /health` - No authentication required

### SKU Management
- `POST /skus` - Create a new SKU with initial stock

### Stock Operations
- `POST /stock/adjust` - Adjust stock level for a SKU

### Reservations
- `POST /reservations` - Create a reservation (requires idempotency_key)
- `POST /reservations/{id}/confirm` - Confirm a reservation
- `POST /reservations/{id}/cancel` - Cancel a reservation

### Orders
- `GET /orders` - Retrieve paginated list of orders

## Authentication

All mutating endpoints require an `X-API-Key` header with a valid API token.
