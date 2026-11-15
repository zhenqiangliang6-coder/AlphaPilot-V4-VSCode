from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.order import Order
from backend.models.enums import OrderStatus
from backend.schemas.order import OrderCreate, OrderResponse, OrderUpdateStatus
from datetime import datetime, timezone

orders_router = APIRouter()

@orders_router.post("/", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order(order: OrderCreate, db: Session = Depends(get_db)):
    db_order = Order(
        user_id=order.user_id,
        total_amount=order.total_amount,
        items=order.items,
        status=order.status.value,
        created_at=datetime.now(timezone.utc)
    )
    db.add(db_order)
    db.commit()
    db.refresh(db_order)
    return db_order

@orders_router.get("/", response_model=List[OrderResponse], status_code=status.HTTP_200_OK)
def list_orders(db: Session = Depends(get_db)):
    return db.query(Order).all()

@orders_router.get("/{order_id}", response_model=OrderResponse, status_code=status.HTTP_200_OK)
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@orders_router.put("/{order_id}/status", response_model=OrderResponse, status_code=status.HTTP_200_OK)
def update_order_status(
    order_id: int,
    status_update: OrderUpdateStatus,
    db: Session = Depends(get_db)
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    try:
        current_status = OrderStatus(order.status)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid current status")

    try:
        new_status_enum = OrderStatus(status_update.new_status)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid new status value")

    allowed_next = current_status.next_states()
    if new_status_enum.value not in allowed_next:
        raise HTTPException(status_code=422, detail="Invalid status transition")

    order.status = new_status_enum.value
    db.commit()
    db.refresh(order)
    return order

@orders_router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    db.delete(order)
    db.commit()
    return None