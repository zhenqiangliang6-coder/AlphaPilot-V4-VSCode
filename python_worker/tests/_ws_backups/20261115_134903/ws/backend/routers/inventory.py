from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.inventory import Inventory
from backend.schemas.inventory import InventoryCreate
from backend.schemas.inventory import InventoryUpdate
from backend.schemas.inventory import InventoryResponse

router = APIRouter()


@router.post("/", response_model=InventoryResponse, status_code=status.HTTP_201_CREATED)
def create_inventory_item(payload: InventoryCreate, db: Session = Depends(get_db)):
    """入库：创建新的库存记录。如果商品已存在则返回 400。"""
    existing_item = db.query(Inventory).filter(
        Inventory.product_name == payload.product_name
    ).first()
    
    if existing_item:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Product '{payload.product_name}' already exists in inventory",
        )

    new_inventory = Inventory(
        product_name=payload.product_name,
        sku=payload.sku,
        quantity=payload.quantity,
        unit_price=payload.unit_price,
    )
    db.add(new_inventory)
    try:
        db.commit()
        db.refresh(new_inventory)
        return new_inventory
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create inventory item: {str(e)}")


@router.get("/", response_model=list[InventoryResponse], status_code=status.HTTP_200_OK)
def list_inventory(db: Session = Depends(get_db)):
    """获取所有库存列表。"""
    items = db.query(Inventory).all()
    return items


@router.get("/{product_name}", response_model=InventoryResponse, status_code=status.HTTP_200_OK)
def get_inventory_by_product(product_name: str, db: Session = Depends(get_db)):
    """查询单品库存。"""
    item = db.query(Inventory).filter(
        Inventory.product_name == product_name
    ).first()
    
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product '{product_name}' not found in inventory",
        )
    return item


@router.patch("/{product_name}", response_model=InventoryResponse, status_code=status.HTTP_200_OK)
def update_inventory_item(
    product_name: str, payload: InventoryUpdate, db: Session = Depends(get_db)
):
    """更新库存（数量或价格）。"""
    item = db.query(Inventory).filter(
        Inventory.product_name == product_name
    ).first()
    
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product '{product_name}' not found in inventory",
        )

    if payload.quantity is not None:
        if payload.quantity < 0:
             raise HTTPException(status_code=400, detail="Quantity cannot be negative")
        item.quantity = payload.quantity
        
    if payload.unit_price is not None:
        if payload.unit_price < 0:
             raise HTTPException(status_code=400, detail="Price cannot be negative")
        item.unit_price = payload.unit_price

    try:
        db.commit()
        db.refresh(item)
        return item
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update inventory item: {str(e)}")