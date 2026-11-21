from enum import Enum


class OrderStatus(str, Enum):
    """订单状态枚举，定义状态及其允许的迁移路径。"""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

    def next_states(self) -> list[str]:
        """
        返回当前状态允许迁移到的下一个状态值列表。
        
        Returns:
            list[str]: 合法的目标状态字符串列表。
        """
        if self == OrderStatus.PENDING:
            return [OrderStatus.CONFIRMED.value, OrderStatus.CANCELLED.value]
        elif self == OrderStatus.CONFIRMED:
            return [OrderStatus.SHIPPED.value, OrderStatus.CANCELLED.value]
        elif self == OrderStatus.SHIPPED:
            return [OrderStatus.DELIVERED.value]
        elif self == OrderStatus.DELIVERED:
            return []
        elif self == OrderStatus.CANCELLED:
            return []
        else:
            return []