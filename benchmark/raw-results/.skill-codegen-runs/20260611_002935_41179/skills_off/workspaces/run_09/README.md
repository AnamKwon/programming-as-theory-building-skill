# Commerce Inventory & Order API

A FastAPI-based service for managing product inventory, reservations, and orders with stock validation and idempotency support.

## Features

- **SKU Management**: Create and manage product SKUs with stock levels
- **Stock Adjustment**: Adjust inventory levels (add or remove stock)
- **Reservation System**: Reserve stock with idempotency and expiration
- **Order Creation**: Convert confirmed reservations into orders
- **Pagination**: Browse orders with configurable page size
- **API Token Authentication**: Secure all mutating endpoints

## Installation

```bash
pip install -e ".[dev]"
```

## Running the Server

```bash
uvicorn commerce_service.app:app --reload
```

## API Documentation

Once the server is running, visit `http://localhost:8000/docs` for interactive API documentation.

## Configuration

Set the `API_TOKEN` environment variable to secure the API:

```bash
export API_TOKEN="your-secret-token"
```

## Testing

```bash
pytest
```
