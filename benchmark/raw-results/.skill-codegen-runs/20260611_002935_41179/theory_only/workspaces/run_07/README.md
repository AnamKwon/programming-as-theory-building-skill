# Commerce Service

A FastAPI-based inventory and order management service with reservation tracking.

## Overview

This service provides APIs for managing product inventory, creating reservations, and processing orders. It includes:
- SKU management with stock tracking
- Reservation system with idempotency support
- Order confirmation and cancellation
- Automatic expiration handling for stale reservations
- API key-based authentication for mutations

## Getting Started

### Installation

```bash
pip install -e ".[dev]"
```

### Running the Server

```bash
uvicorn src.commerce_service.app:app --reload
```

The server will start at `http://127.0.0.1:8000`

### Running Tests

```bash
pytest tests/ -v
```

## API Endpoints

- **GET /health** - Health check (no auth required)
- **POST /skus** - Create a SKU with initial stock
- **POST /stock/adjust** - Adjust stock for a SKU
- **POST /reservations** - Create a reservation
- **POST /reservations/{id}/confirm** - Confirm a reservation
- **POST /reservations/{id}/cancel** - Cancel a reservation
- **GET /orders** - List orders (paginated)

## Authentication

All mutating endpoints (POST, PUT, DELETE) require an API token via `X-API-Key` header.

## Database

SQLite database is automatically created at `commerce.db`
