import uuid
from sqlalchemy import Column, String, Integer, Float
from backend.database import Base


class Inventory(Base):
    """库存模型，使用 SQLAlchemy 经典写法。"""

    __tablename__ = "inventory"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    product_name = Column(String(255), unique=True, nullable=False)
    sku = Column(String(100), nullable=False)
    quantity = Column(Integer, default=0, nullable=False)
    unit_price = Column(Float, default=0.0, nullable=False)

    def __repr__(self):
        return f"<Inventory(id='{self.id}', product_name='{self.product_name}', quantity={self.quantity})>"