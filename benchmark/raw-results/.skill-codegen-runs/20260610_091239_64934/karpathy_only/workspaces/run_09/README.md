# Commerce Service

A production-grade inventory reservation and order orchestration API built with FastAPI.

## Features

- **Health Checks**: Service availability monitoring
- **SKU Management**: Create and manage product SKUs with stock levels
- **Stock Adjustment**: Increase or decrease inventory
- **Reservations**: Create, confirm, and cancel reservations with idempotency support
- **Order Lookup**: Paginated order queries
- **API Security**: API key validation for mutating endpoints
- **Expiration Handling**: Automatic reservation expiration
- **State Transitions**: Enforced order and reservation state machines

## Quick Start

### Installation

```bash
pip install -e ".[dev]"
```

### Running the Service

```bash
python -m uvicorn commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`.

### API Documentation

OpenAPI docs available at `http://localhost:8000/docs`.

### Testing

```bash
pytest tests/ -v
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| POST | `/skus` | Create SKU |
| POST | `/skus/{sku_id}/adjust-stock` | Adjust stock quantity |
| POST | `/reservations` | Create reservation |
| POST | `/reservations/{reservation_id}/confirm` | Confirm reservation |
| POST | `/reservations/{reservation_id}/cancel` | Cancel reservation |
| GET | `/orders` | List orders (paginated) |
| GET | `/orders/{order_id}` | Get order details |

## Architecture

- **app.py**: FastAPI application and endpoint definitions
- **models.py**: Pydantic request/response schemas
- **service.py**: Business logic and domain rules
- **repository.py**: Data access layer with SQLite
- **security.py**: API key authentication

## Database

Uses SQLite for persistence. Database file created at runtime as `commerce.db`.
