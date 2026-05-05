# Qwen Worker v2 Redis 连接诊断指南

## 📋 问题背景

昨天测试 Qwen Worker v2 时出现连接错误，可能是以下原因：
1. **网络/代理问题**：Upstash Redis 在国内访问可能受限
2. **代码问题**：Worker 代码本身存在 bug

## 🔧 解决方案

我们提供了两个工具来诊断问题：

### 1. 独立测试脚本：`test_qwen_worker_v2_redis.py`

这个脚本可以：
- ✅ 测试 Upstash Redis REST API 连接
- ✅ 测试 Python SDK 连接
- ✅ 测试内存模式（绕过云 Redis）
- ✅ 详细输出每个步骤的状态

#### 使用方法

```powershell
# 激活虚拟环境
cd d:\Copilot_Alphapilot\Copilot_Alphapilot
.<venv>\Scripts\Activate.ps1

# 测试 1: 使用云 Redis（默认）
python python_worker/test_qwen_worker_v2_redis.py

# 测试 2: 使用内存模式（绕过云 Redis）
python python_worker/test_qwen_worker_v2_redis.py --use-memory

# 测试 3: 详细日志模式
python python_worker/test_qwen_worker_v2_redis.py --verbose
```

#### 预期输出

**如果云 Redis 正常：**
```
✅ Upstash REST API: 通过
✅ Python SDK: 通过
✅ 内存模式: 通过
✅ Worker 初始化 (云 Redis): 通过
```

**如果云 Redis 有问题：**
```
❌ Upstash REST API: 失败
❌ Python SDK: 失败
✅ 内存模式: 通过
❌ Worker 初始化 (云 Redis): 失败

排查建议:
  1. 检查网络连接和代理配置
  2. 尝试运行: python test_qwen_worker_v2_redis.py --use-memory
  3. 检查 Upstash Redis URL 和 Token 是否正确
```

### 2. Worker 内存模式开关

我们在 `worker_config.py` 中添加了环境变量开关：

```env
# .env 文件
USE_MEMORY_REDIS=true   # 启用内存模式（调试用）
USE_MEMORY_REDIS=false  # 使用云 Redis（生产用）
```

#### 使用方法

**方法 1: 修改 .env 文件**
```env
# 在 python_worker/.env 中添加
USE_MEMORY_REDIS=true
```

**方法 2: 设置环境变量**
```powershell
$env:USE_MEMORY_REDIS="true"
python -m python_worker.agents.qwen.qwen_worker_v2
```

## 🎯 诊断流程

### 步骤 1: 运行独立测试脚本

```powershell
# 先测试云 Redis
python python_worker/test_qwen_worker_v2_redis.py

# 再测试内存模式
python python_worker/test_qwen_worker_v2_redis.py --use-memory
```

**判断标准：**
- 如果 **云 Redis 失败** 但 **内存模式成功** → 网络/代理问题
- 如果 **两者都失败** → 代码问题
- 如果 **两者都成功** → 可能是其他配置问题

### 步骤 2: 根据结果采取行动

#### 情况 A: 网络/代理问题

如果云 Redis 测试失败，尝试以下方案：

**方案 1: 配置代理**
```powershell
# 设置 HTTP 代理
$env:HTTP_PROXY="http://127.0.0.1:7890"
$env:HTTPS_PROXY="http://127.0.0.1:7890"

# 重新测试
python python_worker/test_qwen_worker_v2_redis.py
```

**方案 2: 切换到国内 Redis 服务**
```env
# 在 .env 中使用阿里云 Redis（已在 .env 中配置）
REDIS_HOST=redis-10912.crce264.ap-east-1-1.ec2.cloud.redislabs.com
REDIS_PORT=10912
REDIS_USERNAME=default
REDIS_PASSWORD=TchBYuSAPZ9Te7lyGXvyktqeNLTjoFy5
REDIS_TLS=true
```

**方案 3: 临时使用内存模式**
```env
# 在 .env 中设置
USE_MEMORY_REDIS=true
```

#### 情况 B: 代码问题

如果内存模式也失败，说明是代码问题：

1. 查看测试脚本的详细错误输出
2. 检查 `qwen_worker_v2.py` 的代码逻辑
3. 运行单元测试：
   ```powershell
   python python_worker/test_qwen_worker_v2.py
   ```

### 步骤 3: 验证修复

修复后，再次运行测试：

```powershell
# 测试云 Redis
python python_worker/test_qwen_worker_v2_redis.py

# 如果成功，启动 Worker
$env:WORKER_ID="qwen-worker-1"
python -m python_worker.agents.qwen.qwen_worker_v2
```

## 📊 测试结果解读

### 测试 1: 环境变量检查

检查以下变量是否配置：
- `UPSTASH_REDIS_REST_URL`
- `UPSTASH_REDIS_REST_TOKEN`
- `DASHSCOPE_API_KEY`
- `WORKER_ID`

### 测试 2: Upstash REST API

直接调用 Upstash 的 REST API：
- `POST /ping` - 测试连接
- `POST /set/{key}/{value}` - 测试写入
- `GET /get/{key}` - 测试读取

**常见错误：**
- `Timeout` - 网络超时，检查代理
- `ConnectionError` - DNS 或防火墙问题
- `401 Unauthorized` - Token 错误

### 测试 3: Python SDK

使用 `upstash-redis` 库测试：
- `redis.ping()`
- `redis.set()` / `redis.get()`

**常见错误：**
- `ImportError` - 库未安装，运行 `pip install upstash-redis`
- `AuthenticationError` - Token 无效

### 测试 4: 内存模式

使用内存字典模拟 Redis：
- 不依赖网络
- 用于隔离代码问题

**如果此测试失败** → 肯定是代码问题

### 测试 5: Worker 初始化

模拟完整的 Worker 启动流程：
- 创建 Redis 客户端
- 推送测试任务到队列
- 从队列弹出任务

**如果此测试失败** → Worker 代码有问题

## 🔍 常见问题

### Q1: 如何知道是网络问题还是代码问题？

**答：** 运行内存模式测试：
```powershell
python python_worker/test_qwen_worker_v2_redis.py --use-memory
```
- 如果内存模式成功 → 网络问题
- 如果内存模式失败 → 代码问题

### Q2: 如何配置代理？

**答：**
```powershell
# Windows PowerShell
$env:HTTP_PROXY="http://127.0.0.1:7890"
$env:HTTPS_PROXY="http://127.0.0.1:7890"

# 或在 Python 代码中设置
import os
os.environ['HTTP_PROXY'] = 'http://127.0.0.1:7890'
os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:7890'
```

### Q3: 内存模式会影响功能吗？

**答：** 
- ✅ 内存模式仅用于**调试**，不会影响代码逻辑
- ❌ 内存模式**不支持分布式**，重启后数据丢失
- ⚠️ 生产环境请使用云 Redis

### Q4: 如何切换回云 Redis？

**答：**
```env
# 方法 1: 修改 .env 文件
USE_MEMORY_REDIS=false

# 方法 2: 删除该环境变量
# 在 .env 中注释掉或删除 USE_MEMORY_REDIS 行
```

## 📝 快速参考

### 命令速查

```powershell
# 测试云 Redis
python python_worker/test_qwen_worker_v2_redis.py

# 测试内存模式
python python_worker/test_qwen_worker_v2_redis.py --use-memory

# 详细日志
python python_worker/test_qwen_worker_v2_redis.py --verbose

# 启动 Worker（内存模式）
$env:USE_MEMORY_REDIS="true"
$env:WORKER_ID="qwen-worker-1"
python -m python_worker.agents.qwen.qwen_worker_v2

# 启动 Worker（云 Redis）
$env:USE_MEMORY_REDIS="false"
$env:WORKER_ID="qwen-worker-1"
python -m python_worker.agents.qwen.qwen_worker_v2
```

### 环境变量速查

```env
# .env 文件
USE_MEMORY_REDIS=true       # 启用内存模式
USE_MEMORY_REDIS=false      # 使用云 Redis（默认）

UPSTASH_REDIS_REST_URL=https://winning-treefrog-111773.upstash.io
UPSTASH_REDIS_REST_TOKEN=gQAAAAAAAbSdAAIgcDJhNzhhZmRiYzc3NjA0YzhkOTZiZjIwNmE4OWI1ZjVhMg
```

## 🎉 总结

通过这两个工具，你可以快速定位问题：

1. **运行测试脚本** → 确定是网络问题还是代码问题
2. **使用内存模式** → 绕过网络问题，专注代码调试
3. **修复后验证** → 确保问题已解决

祝调试顺利！✨
