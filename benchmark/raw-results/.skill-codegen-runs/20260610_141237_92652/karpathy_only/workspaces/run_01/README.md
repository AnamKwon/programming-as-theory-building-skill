# Commerce Inventory & Order API

A FastAPI-based service for managing SKU inventory, reservations, and orders.

## Features

- SKU inventory management
- Stock reservation with idempotency
- Reservation confirmation with expiration validation
- Order tracking with pagination
- API token-based authentication for mutations

## Installation

```bash
pip install -e .
pip install -e ".[dev]"
```

## Running the Service

```bash
uvicorn commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`

## Running Tests

```bash
pytest tests/
```

## API Endpoints

- `GET /health` - Health check
- `POST /skus` - Create a SKU
- `POST /stock/adjust` - Adjust stock level
- `POST /reservations` - Create a reservation
- `POST /reservations/{id}/confirm` - Confirm a reservation
- `POST /reservations/{id}/cancel` - Cancel a reservation
- `GET /orders` - List orders (paginated)

## Authentication

All mutating endpoints require an `X-API-Key` header with the valid API token.
