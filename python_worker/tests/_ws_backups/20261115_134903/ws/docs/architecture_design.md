# ShopFlow Backend 架构设计文档

## 1. 模块划分与职责

本系统采用分层架构，各模块职责明确，确保代码的高内聚低耦合：

- **models/**: 数据模型层。负责定义 SQLAlchemy ORM 模型类以及业务枚举（如 `OrderStatus`）。此层直接映射数据库表结构，不包含任何业务逻辑或 HTTP 处理代码。
- **routers/**: 路由层（Controller）。负责接收 HTTP 请求，解析参数，调用服务层处理业务，并返回响应。此层仅关注接口契约（Method, Path, Status Code），不处理具体业务规则。
- **services/**: 业务逻辑层。核心业务处理所在区域，包括订单创建、状态流转校验、金额计算等。此层隔离了路由层与数据访问层，便于单元测试和业务复用。
- **schemas/**: 数据验证与序列化层。使用 Pydantic 模型定义 API 的请求体（Request Body）和响应体（Response Model）。负责输入数据的合法性校验及输出数据的格式化。
- **tests/**: 测试层。包含单元测试与集成测试，覆盖服务层逻辑与 API 端点行为，确保系统稳定性。

## 2. 数据模型设计

### Order 实体字段
`Order` 是系统的核心实体，其字段定义如下：
- `id`: Integer, Primary Key, Auto Increment。订单唯一标识。
- `user_id`: Integer, Foreign Key。关联的用户 ID。
- `status`: String/Enum。订单当前状态，默认值为 `pending`。
- `total_amount`: Float/Decimal。订单总金额。
- `items`: JSON。订单项列表，存储为 JSON 列。**注意**：不设独立的订单项 ORM 表，也不新增订单项模型类，所有商品明细统一存入此 JSON 字段。
- `created_at`: DateTime。订单创建时间，自动记录。

### Items JSON 列结构示例
`items` 字段存储一个对象数组，每个对象代表一个商品项：
[
  {
    "product_id": 101,
    "name": "Wireless Mouse",
    "quantity": 2,
    "unit_price": 25.00
  },
  {
    "product_id": 205,
    "name": "Mechanical Keyboard",
    "quantity": 1,
    "unit_price": 89.99
  }
]

## 3. OrderStatus 枚举

状态定义集中在 `models` 包内的枚举模块中，确保状态值的统一管理。
枚举值及流转关系如下：
- `PENDING`: 待支付/初始状态
- `CONFIRMED`: 已确认/已支付
- `SHIPPED`: 已发货
- `DELIVERED`: 已送达
- `CANCELLED`: 已取消

**状态流转规则**：
`PENDING` → `CONFIRMED` → `SHIPPED` → `DELIVERED`
任意非终态可流向 `CANCELLED`（具体业务规则由 Service 层控制）。

## 4. API 契约

所有 API 端点均挂载在 `/orders` 前缀下（由 `main.py` 统一配置），Router 文件内部只定义相对路径。

| Method | Path (Relative) | Full Path | Request Body | Response Format | Status Code | Description |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| POST | `/` | `/orders` | `{ user_id, items }` | `{ id, status, total_amount, ... }` | 200 | 创建新订单 |
| GET | `/` | `/orders` | None | `[ { order_obj_1 }, { order_obj_2 } ]` | 200 | 查询订单列表 |
| GET | `/{order_id}` | `/orders/{order_id}` | None | `{ id, status, total_amount, ... }` | 200 | 查询单个订单详情 |
| PUT | `/{order_id}/status` | `/orders/{order_id}/status` | `{ new_status }` | `{ id, status, updated_at, ... }` | 200 | 更新订单状态 |
| DELETE | `/{order_id}` | `/orders/{order_id}` | None | None | 204 | 删除订单 |

*注：响应格式中的 `...` 表示包含其他标准字段如 `user_id`, `items`, `created_at` 等。*

## 5. 数据流

系统遵循标准的 MVC + Service 分层数据流：

1. **Client Request**: 客户端发送 HTTP 请求至 FastAPI 应用。
2. **Routing Layer (`routers/`)**: 
   - 匹配 URL 路径与 HTTP 方法。
   - 提取路径参数（如 `order_id`）和请求体。
   - 将请求委托给 Service 层。
3. **Service Layer (`services/`)**:
   - 执行业务逻辑（如验证状态流转是否合法、计算总价）。
   - 调用 Model 层进行数据持久化或查询。
4. **Model Layer (`models/`)**:
   - SQLAlchemy ORM 对象与数据库交互。
   - 执行 SQL 语句（INSERT, SELECT, UPDATE, DELETE）。
5. **Database (SQLite)**: 存储实际数据。
6. **Schema Serialization (`schemas/`)**:
   - Service 返回 ORM 对象或字典。
   - Router 层利用 Pydantic Schema 将结果序列化为 JSON。
7. **HTTP Response**: 返回格式化后的 JSON 数据及对应状态码给客户端。

## 6. 技术栈

- **Web Framework**: FastAPI (高性能异步 Web 框架)
- **ORM**: SQLAlchemy (Python SQL Toolkit and Object Relational Mapper)
- **Database**: SQLite (轻量级嵌入式数据库，适用于开发与测试环境)
- **Testing**: pytest (Python 测试框架)
- **Data Validation**: Pydantic (FastAPI 内置依赖，用于 Schemas 定义)