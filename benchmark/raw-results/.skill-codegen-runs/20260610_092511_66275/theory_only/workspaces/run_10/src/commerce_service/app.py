"""FastAPI application."""

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from .models import (
    InventoryResponse,
    OrderListResponse,
    OrderResponse,
    ReservationCreate,
    ReservationResponse,
    SKUCreate,
    SKUResponse,
    StockAdjust,
)
from .repository import Repository, get_db, init_db
from .security import verify_api_key
from .service import CommercService, ConflictError, NotFoundError, ValidationError

app = FastAPI(title="Commerce Service", version="0.1.0")


@app.on_event("startup")
def startup_event():
    """Initialize database on startup."""
    init_db()


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "ok"}


# SKU Endpoints


@app.post("/skus", response_model=SKUResponse)
def create_sku(sku: SKUCreate, db: Session = Depends(get_db), api_key: str = Depends(verify_api_key)):
    """Create a new SKU."""
    try:
        repo = Repository(db)
        service = CommercService(repo)
        sku_obj = service.create_sku(sku.id, sku.name)
        return sku_obj
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/skus/{sku_id}", response_model=SKUResponse)
def get_sku(sku_id: str, db: Session = Depends(get_db)):
    """Get SKU details."""
    try:
        repo = Repository(db)
        service = CommercService(repo)
        sku = service.get_sku(sku_id)
        return sku
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


# Inventory Endpoints


@app.get("/inventory/{sku_id}", response_model=InventoryResponse)
def get_inventory(sku_id: str, db: Session = Depends(get_db)):
    """Get current inventory state."""
    try:
        repo = Repository(db)
        service = CommercService(repo)
        inventory = service.get_inventory(sku_id)
        return inventory
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/inventory/{sku_id}/adjust", response_model=InventoryResponse)
def adjust_stock(
    sku_id: str, adjustment: StockAdjust, db: Session = Depends(get_db), api_key: str = Depends(verify_api_key)
):
    """Adjust stock quantity for a SKU."""
    try:
        repo = Repository(db)
        service = CommercService(repo)
        inventory = service.adjust_stock(sku_id, adjustment.quantity_change)
        return inventory
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


# Reservation Endpoints


@app.post("/reservations", response_model=ReservationResponse)
def create_reservation(
    res: ReservationCreate, db: Session = Depends(get_db), api_key: str = Depends(verify_api_key)
):
    """Create a reservation."""
    try:
        repo = Repository(db)
        service = CommercService(repo)
        reservation = service.create_reservation(
            sku_id=res.sku_id,
            order_id=res.order_id,
            quantity=res.quantity,
            ttl_seconds=res.ttl_seconds,
            idempotency_key=res.idempotency_key,
        )
        return reservation
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/reservations/{reservation_id}", response_model=ReservationResponse)
def get_reservation(reservation_id: str, db: Session = Depends(get_db)):
    """Get reservation details."""
    try:
        repo = Repository(db)
        service = CommercService(repo)
        reservation = service.get_reservation(reservation_id)
        return reservation
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
def confirm_reservation(
    reservation_id: str, db: Session = Depends(get_db), api_key: str = Depends(verify_api_key)
):
    """Confirm a pending reservation."""
    try:
        repo = Repository(db)
        service = CommercService(repo)
        reservation = service.confirm_reservation(reservation_id)
        return reservation
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
def cancel_reservation(
    reservation_id: str, db: Session = Depends(get_db), api_key: str = Depends(verify_api_key)
):
    """Cancel a pending reservation."""
    try:
        repo = Repository(db)
        service = CommercService(repo)
        reservation = service.cancel_reservation(reservation_id)
        return reservation
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


# Order Endpoints


@app.get("/orders/{order_id}", response_model=OrderResponse)
def get_order(order_id: str, db: Session = Depends(get_db)):
    """Get order details."""
    try:
        repo = Repository(db)
        service = CommercService(repo)
        order = service.get_order(order_id)
        return order
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/orders", response_model=OrderListResponse)
def list_orders(page: int = 1, page_size: int = 10, db: Session = Depends(get_db)):
    """List orders with pagination."""
    try:
        repo = Repository(db)
        service = CommercService(repo)
        result = service.list_orders(page=page, page_size=page_size)
        return OrderListResponse(
            orders=result["orders"],
            total=result["total"],
            page=result["page"],
            page_size=result["page_size"],
            has_more=result["has_more"],
        )
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
