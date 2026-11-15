from enum import Enum
from typing import List, ClassVar, Dict, Any

class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

    _transitions: ClassVar[Dict["OrderStatus", List["OrderStatus"]]] = {
        PENDING: [CONFIRMED, CANCELLED],
        CONFIRMED: [SHIPPED, CANCELLED],
        SHIPPED: [DELIVERED, CANCELLED],
        DELIVERED: [CANCELLED],
        CANCELLED: [],
    }

    def next_states(self) -> List[str]:
        return [s.value for s in self._transitions.get(self, [])]