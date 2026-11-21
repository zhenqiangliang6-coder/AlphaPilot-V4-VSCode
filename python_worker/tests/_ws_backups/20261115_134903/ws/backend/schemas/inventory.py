from pydantic import BaseModel, Field
from typing import Optional


class InventoryBase(BaseModel):
    product_name: str = Field(..., description="商品名称")
    sku: str = Field(..., description="SKU编码")
    quantity: int = Field(..., ge=0, description="库存数量")
    unit_price: float = Field(..., ge=0, description="单价")


class InventoryCreate(InventoryBase):
    pass


class InventoryUpdate(BaseModel):
    quantity: Optional[int] = Field(None, ge=0, description="更新后的库存数量")
    unit_price: Optional[float] = Field(None, ge=0, description="更新后的单价")


class InventoryResponse(InventoryBase):
    id: str = Field(..., description="库存记录ID")

    class Config:
        from_attributes = True