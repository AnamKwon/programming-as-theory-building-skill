# Commerce Inventory & Order API

A FastAPI-based inventory and order management system with reservation support, stock management, and order fulfillment workflows.

## Features

- **SKU Management**: Create and track product SKUs with stock levels
- **Stock Adjustment**: Adjust inventory levels for received/lost stock
- **Reservations**: Reserve stock with idempotency and expiration validation
- **Order Fulfillment**: Confirm reservations to create orders
- **Pagination**: List orders with configurable pagination
- **Security**: API token-based authentication for mutating operations
- **Invariant Enforcement**: Expiration checks and state validation

## Quick Start

### Installation

```bash
pip install -e .
pip install -e ".[dev]"
```

### Running the Server

```bash
uvicorn commerce_service.app:app --reload
```

The server will start on `http://localhost:8000`

### Running Tests

```bash
pytest tests/
```

## API Endpoints

### Health Check
- `GET /health` - Returns service status (no auth required)

### SKU Management
- `POST /skus` - Create a new SKU with initial stock
- `POST /stock/adjust` - Adjust stock for a SKU

### Reservations
- `POST /reservations` - Create a reservation (idempotency-enabled)
- `POST /reservations/{id}/confirm` - Confirm and create order
- `POST /reservations/{id}/cancel` - Cancel and restore stock

### Orders
- `GET /orders` - List orders with pagination

## Authentication

Mutating endpoints (POST, PUT, DELETE) require a valid API token in the request header:

```
Authorization: Bearer YOUR_API_TOKEN
```

Default test token: `test-token-secret`

## Database

SQLite database for local development. Database file created at runtime in the application directory.
