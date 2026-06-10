# Commerce Service

A production-grade inventory reservation and order orchestration API built with FastAPI, Pydantic, and SQLite.

## Features

- **Inventory Management**: Create SKUs and manage stock levels
- **Reservation System**: Reserve inventory with automatic expiration
- **Order Orchestration**: Confirm reservations into orders with state transitions
- **Idempotency**: Safe retry semantics via idempotency keys
- **Security**: API key validation on mutating endpoints
- **Pagination**: Browse orders with offset-limit pagination

## Quick Start

### Installation

```bash
pip install -e ".[dev]"
```

### Run the service

```bash
uvicorn commerce_service.app:app --reload
```

Server starts on `http://localhost:8000`

### Run tests

```bash
pytest
```

## API Endpoints

### Health
- `GET /health` - Service status

### SKUs
- `POST /skus` - Create a SKU
- `POST /skus/{sku_id}/adjust-stock` - Adjust inventory level

### Reservations
- `POST /reservations` - Create a reservation
- `POST /reservations/{reservation_id}/confirm` - Confirm to order
- `POST /reservations/{reservation_id}/cancel` - Cancel reservation

### Orders
- `GET /orders` - List orders with pagination

## Design

- **Models**: Pydantic schemas for validation
- **Repository**: SQLite data access layer
- **Service**: Business logic and state transitions
- **Security**: API key dependency injection
- **API**: FastAPI routes with error handling

Reservations expire after 15 minutes. Confirmed orders persist indefinitely.
