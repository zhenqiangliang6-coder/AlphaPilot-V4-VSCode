#  紧急修复: NODE_API_URL 未定义

## 问题现象

```
️ 通知 Node.js 失败: name 'NODE_API_URL' is not defined
   结果已保存在 Redis，但前端可能无法实时收到
```

## 根本原因

**qwen_worker_v2.py 中使用了 `NODE_API_URL` 变量,但没有导入它!**

```python
#  错误: 没有导入 NODE_API_URL
notify_url = f"{NODE_API_URL}/task/notify/{task_id}"
```

## 修复内容

### 1. ✅ 添加 NODE_API_URL 导入

**文件**: `python_worker/agents/qwen/qwen_worker_v2.py`

```python
from ...worker_config import (
    redis,
    WORKER_ID,
    create_empty_context,
    check_stop_flag,
    clear_stop_flag,
    get_worker_queue,
    NODE_API_URL,  # ⭐ 新增
)
```

### 2. ✅ 添加 requests 模块导入

```python
import requests  # ⭐ 新增: 用于调用 /task/notify
```

## 验证

### worker_config.py 中已定义

```python
# worker_config.py 第75行
NODE_API_URL = os.getenv("NODE_API_URL", "http://localhost:3000")
```

### 修复后的完整导入

```python
import json
import time
import traceback
import requests  # ⭐ 新增

from ...worker_config import (
    redis,
    WORKER_ID,
    create_empty_context,
    check_stop_flag,
    clear_stop_flag,
    get_worker_queue,
    NODE_API_URL,  # ⭐ 新增
)
```

## 下一步

**重启 Qwen Worker v2**,现在应该能看到:

```
 正在通知 Node.js: http://localhost:3000/task/notify/af80bc14-...
✅ Node.js 已成功接收通知，将推送给前端
```

然后前端就会显示输出了!

---

*修复时间: 2026-05-04*  
*状态: ✅ 已完成,需要重启 Worker*
