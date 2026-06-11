# Commerce Inventory & Order API

A FastAPI-based service for managing SKU inventory, stock reservations, and order fulfillment.

## Features

- **SKU Management**: Create and manage SKUs with stock levels
- **Stock Adjustment**: Increase or decrease available stock
- **Reservations**: Reserve stock with idempotency guarantees and automatic expiration
- **Order Management**: Confirm reservations and create orders
- **Pagination**: Browse orders with configurable page size
- **API Authentication**: Static token-based authentication for mutations

## Installation

```bash
pip install -e .
pip install -e ".[dev]"
```

## Running the Application

```bash
uvicorn src.commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`.

## API Endpoints

### Health Check
- `GET /health` - Health status

### SKU Management
- `POST /skus` - Create SKU
- `POST /stock/adjust` - Adjust stock level

### Reservations
- `POST /reservations` - Create a reservation
- `POST /reservations/{id}/confirm` - Confirm a pending reservation
- `POST /reservations/{id}/cancel` - Cancel a reservation

### Orders
- `GET /orders` - List orders (paginated)

## Testing

```bash
pytest -v
```

## Environment Variables

- `API_TOKEN` - Static token for mutation authentication (default: `secret-token`)
