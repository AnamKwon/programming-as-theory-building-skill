# Commerce Service

Inventory reservation and order orchestration API built with FastAPI.

## Features

- **SKU Management:** Create and manage product stock
- **Stock Adjustment:** Add or remove inventory
- **Reservations:** Temporary inventory holds with expiration
- **Orders:** Confirmed purchases from reservations
- **Idempotency:** Safe request retry with idempotency keys
- **Authentication:** API-key based access control for mutations
- **Pagination:** Efficient order listing

## Running

Install dependencies:
```bash
pip install -e ".[dev]"
```

Start the server:
```bash
uvicorn commerce_service.app:app --reload
```

Run tests:
```bash
pytest
```

## API Endpoints

### Health Check
- `GET /health` - Service status

### SKU Management
- `POST /skus` - Create SKU (requires API key)
- `GET /skus/{sku_id}` - Get SKU details

### Stock Management
- `POST /stock/adjust` - Adjust inventory (requires API key)

### Reservations
- `POST /reservations` - Create reservation (requires API key)
- `POST /reservations/{reservation_id}/confirm` - Confirm reservation (requires API key)
- `POST /reservations/{reservation_id}/cancel` - Cancel reservation (requires API key)

### Orders
- `GET /orders` - List orders with pagination

## Architecture

- **models.py:** Database models and schemas
- **repository.py:** Data access layer
- **service.py:** Business logic and rules
- **security.py:** Authentication
- **app.py:** FastAPI application and endpoints
