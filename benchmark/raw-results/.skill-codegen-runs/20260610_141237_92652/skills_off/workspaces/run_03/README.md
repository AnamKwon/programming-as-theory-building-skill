# Commerce Inventory & Order API

A FastAPI-based inventory and order management system with stock reservation, expiration handling, and idempotency support.

## Features

- **SKU Management**: Create and manage product SKUs with stock levels
- **Stock Adjustment**: Adjust inventory levels up or down
- **Reservation System**: Reserve stock with built-in idempotency and expiration
- **Order Management**: Convert confirmed reservations to orders with pagination
- **API Token Security**: All mutations require authentication
- **Idempotent Operations**: Duplicate requests with same idempotency key return cached responses

## Installation

```bash
pip install -e .
```

## Running the Server

```bash
uvicorn commerce_service.app:app --reload
```

The server runs on `http://localhost:8000`.

## API Documentation

Interactive API docs available at `http://localhost:8000/docs`

## Testing

```bash
pytest tests/
```
