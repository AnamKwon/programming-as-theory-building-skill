# Commerce Service - Inventory & Order API

A FastAPI-based service for managing product inventory, reservations, and orders with strong consistency guarantees.

## Features

- **SKU Management**: Create and manage product SKUs with stock levels
- **Stock Adjustments**: Adjust inventory in real-time
- **Reservations**: Reserve inventory with idempotency and expiration
- **Orders**: Confirm reservations and generate orders with pagination
- **Security**: API token-based authentication for mutating operations
- **State Management**: Strict state validation and time-based expiration (300 seconds)

## Quick Start

### Installation

```bash
pip install -e .
pip install -e ".[dev]"  # For development and testing
```

### Running the Server

```bash
uvicorn src.commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`

### Running Tests

```bash
pytest tests/ -v
```

## API Endpoints

### Health Check
- `GET /health` - Returns service status (no authentication required)

### SKU Management
- `POST /skus` - Create a new SKU with initial stock (requires API token)

### Stock Operations
- `POST /stock/adjust` - Adjust stock levels for a SKU (requires API token)

### Reservations
- `POST /reservations` - Create a reservation (requires API token)
- `POST /reservations/{id}/confirm` - Confirm a pending reservation (requires API token)
- `POST /reservations/{id}/cancel` - Cancel a pending reservation (requires API token)

### Orders
- `GET /orders` - List orders with pagination (requires API token)

## Authentication

All mutating endpoints require an API token in the Authorization header:

```
Authorization: Bearer YOUR_API_TOKEN
```

The default token for development is `test-token-12345`.

## Database

This service uses SQLite for persistent storage. The database file is automatically created on first run.

## Development

The codebase follows a layered architecture:
- `app.py`: FastAPI application and route handlers
- `models.py`: Database models and Pydantic schemas
- `service.py`: Business logic and workflows
- `repository.py`: Data access layer
- `security.py`: Authentication and authorization
