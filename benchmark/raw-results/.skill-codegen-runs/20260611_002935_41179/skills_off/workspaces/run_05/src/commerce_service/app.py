from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from commerce_service.repository import engine, Base, SessionLocal
from commerce_service.service import CommerceService
from commerce_service.security import verify_api_token
from commerce_service.models import (
    SKUCreate, SKUResponse,
    StockAdjustRequest, StockAdjustResponse,
    ReservationCreate, ReservationResponse,
    OrderResponse, OrderListResponse, PaginationMeta,
    HealthResponse
)

app = FastAPI(title="Commerce Service API")


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_sku_name_from_reservation(reservation) -> str:
    """Helper to get SKU name from reservation"""
    db = SessionLocal()
    try:
        from commerce_service.repository import SKU
        sku = db.query(SKU).filter(SKU.id == reservation.sku_id).first()
        return sku.sku if sku else ""
    finally:
        db.close()


@app.get("/health", response_model=HealthResponse)
def health():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, status_code=201, dependencies=[Depends(verify_api_token)])
def create_sku(sku_data: SKUCreate, db: Session = Depends(get_db)):
    service = CommerceService(db)
    try:
        db_sku = service.create_sku(sku_data.sku, sku_data.initial_stock)
        return db_sku
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/stock/adjust", response_model=StockAdjustResponse, status_code=200, dependencies=[Depends(verify_api_token)])
def adjust_stock(adjust_data: StockAdjustRequest, db: Session = Depends(get_db)):
    service = CommerceService(db)
    try:
        new_stock = service.adjust_stock(adjust_data.sku, adjust_data.amount)
        return {"sku": adjust_data.sku, "new_stock": new_stock}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations", response_model=ReservationResponse, status_code=201, dependencies=[Depends(verify_api_token)])
def create_reservation(res_data: ReservationCreate, db: Session = Depends(get_db)):
    service = CommerceService(db)
    try:
        reservation, status_code = service.create_reservation(
            res_data.sku,
            res_data.quantity,
            res_data.idempotency_key
        )

        sku_name = get_sku_name_from_reservation(reservation)
        response = ReservationResponse(
            id=reservation.id,
            sku=sku_name,
            quantity=reservation.quantity,
            status=reservation.status,
            created_at=reservation.created_at,
            idempotency_key=reservation.idempotency_key
        )

        if status_code == 200:
            return response
        return response
    except ValueError as e:
        if "Insufficient stock" in str(e):
            raise HTTPException(status_code=400, detail="Insufficient stock")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse, status_code=200, dependencies=[Depends(verify_api_token)])
def confirm_reservation(reservation_id: int, db: Session = Depends(get_db)):
    service = CommerceService(db)
    try:
        reservation = service.confirm_reservation(reservation_id)
        sku_name = get_sku_name_from_reservation(reservation)
        return ReservationResponse(
            id=reservation.id,
            sku=sku_name,
            quantity=reservation.quantity,
            status=reservation.status,
            created_at=reservation.created_at,
            idempotency_key=reservation.idempotency_key
        )
    except ValueError as e:
        if "expired" in str(e).lower():
            raise HTTPException(status_code=400, detail="Reservation expired")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse, status_code=200, dependencies=[Depends(verify_api_token)])
def cancel_reservation(reservation_id: int, db: Session = Depends(get_db)):
    service = CommerceService(db)
    try:
        reservation = service.cancel_reservation(reservation_id)
        sku_name = get_sku_name_from_reservation(reservation)
        return ReservationResponse(
            id=reservation.id,
            sku=sku_name,
            quantity=reservation.quantity,
            status=reservation.status,
            created_at=reservation.created_at,
            idempotency_key=reservation.idempotency_key
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/orders", response_model=OrderListResponse, status_code=200, dependencies=[Depends(verify_api_token)])
def list_orders(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1),
    db: Session = Depends(get_db)
):
    service = CommerceService(db)
    try:
        orders, total = service.get_orders(page, size)
        total_pages = (total + size - 1) // size
        return OrderListResponse(
            data=[OrderResponse.model_validate(order) for order in orders],
            meta=PaginationMeta(
                page=page,
                size=size,
                total=total,
                total_pages=total_pages
            )
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
