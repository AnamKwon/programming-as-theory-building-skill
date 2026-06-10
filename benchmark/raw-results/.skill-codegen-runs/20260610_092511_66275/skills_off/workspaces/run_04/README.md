# Commerce Service

Inventory reservation and order orchestration API for small commerce backends.

## Setup

```bash
pip install -e .
pip install -e ".[dev]"
```

## Running

```bash
uvicorn commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`.

## API Endpoints

- `GET /health` - Health check
- `POST /skus` - Create a SKU
- `POST /stock/{product_id}/adjust` - Adjust stock for a product
- `POST /reservations` - Create a reservation (requires API key)
- `POST /reservations/{reservation_id}/confirm` - Confirm a reservation (requires API key)
- `POST /reservations/{reservation_id}/cancel` - Cancel a reservation (requires API key)
- `GET /orders` - List orders with pagination (requires API key)
- `GET /orders/{order_id}` - Get order details

## Authentication

Mutating endpoints require an `X-API-Key` header. Default key is `test-key-123`.

## Features

- **Idempotent Reservations**: Use idempotency keys to safely retry reservation creation
- **Reservation Expiration**: Reservations expire after 15 minutes of inactivity
- **Stock Management**: Real-time stock tracking with adjustment endpoints
- **Order Tracking**: Full order lifecycle from reservation to confirmation
- **Pagination**: Order listing supports limit and offset parameters

## Testing

```bash
pytest tests/
```
