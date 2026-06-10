# Commerce Service

Inventory reservation and order orchestration API for small commerce backends.

## Design

- **SKU**: Product identifiers with stock quantities.
- **Reservation**: Temporary hold on inventory with a TTL (default: 15 minutes). Idempotency keys prevent duplicate reservations for the same logical request.
- **Order**: Confirmed reservation that becomes a persistent sales record.
- **Service Layer**: Enforces stock availability, idempotency, expiration, and state transitions.
- **Repository**: SQLite database access, isolated from business logic.

## Running

```bash
pip install -e .[dev]
uvicorn src.commerce_service.app:app --reload
```

## API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/health` | Health check |
| POST | `/skus` | Create SKU (requires API key) |
| PATCH | `/skus/{sku_id}/adjust-stock` | Adjust stock (requires API key) |
| POST | `/reservations` | Create reservation (idempotent) |
| POST | `/reservations/{reservation_id}/confirm` | Confirm reservation (requires API key) |
| POST | `/reservations/{reservation_id}/cancel` | Cancel reservation (requires API key) |
| GET | `/orders` | List orders with pagination (requires API key) |

## Testing

```bash
pytest tests/
```

## Environment Variables

- `API_KEY`: Secret key for protected endpoints (default: `dev-key`)
