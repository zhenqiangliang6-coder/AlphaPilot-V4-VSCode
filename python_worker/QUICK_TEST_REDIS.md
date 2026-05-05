# Qwen Worker v2 快速测试指南

## 🚀 快速开始

### 方法 1: 使用交互式脚本（推荐）

```powershell
cd d:\Copilot_Alphapilot\Copilot_Alphapilot
.\test_qwen_worker.ps1
```

然后按照菜单选择：
- **选项 1**: 测试云 Redis 连接
- **选项 2**: 测试内存模式
- **选项 3**: 启动 Worker（云 Redis）
- **选项 4**: 启动 Worker（内存模式）

### 方法 2: 直接运行测试脚本

```powershell
# 激活虚拟环境
cd d:\Copilot_Alphapilot\Copilot_Alphapilot
.<.venv_worker\Scripts\Activate.ps1

# 测试云 Redis
$env:WORKER_ID="qwen-worker-1"
python python_worker/test_qwen_worker_v2_redis.py

# 测试内存模式
$env:WORKER_ID="qwen-worker-1"
python python_worker/test_qwen_worker_v2_redis.py --use-memory

# 详细日志
$env:WORKER_ID="qwen-worker-1"
python python_worker/test_qwen_worker_v2_redis.py --verbose
```

## 📊 测试结果解读

### ✅ 所有测试通过

**结论**: 网络和代码都没有问题，可以正常使用。

**下一步**: 
```powershell
# 启动 Worker
$env:WORKER_ID="qwen-worker-1"
python -m python_worker.agents.qwen.qwen_worker_v2
```

### ❌ 云 Redis 失败，内存模式成功

**结论**: 网络/代理问题，代码正常。

**解决方案**:

**方案 A: 配置代理**
```powershell
$env:HTTP_PROXY="http://127.0.0.1:7890"
$env:HTTPS_PROXY="http://127.0.0.1:7890"
python python_worker/test_qwen_worker_v2_redis.py
```

**方案 B: 临时使用内存模式**
```powershell
# 在 .env 文件中添加
USE_MEMORY_REDIS=true

# 或使用命令行
$env:USE_MEMORY_REDIS="true"
python -m python_worker.agents.qwen.qwen_worker_v2
```

**方案 C: 切换到国内 Redis**
```env
# 在 .env 中注释掉 Upstash，启用阿里云 Redis
# UPSTASH_REDIS_REST_URL=...
# UPSTASH_REDIS_REST_TOKEN=...

REDIS_HOST=redis-10912.crce264.ap-east-1-1.ec2.cloud.redislabs.com
REDIS_PORT=10912
REDIS_USERNAME=default
REDIS_PASSWORD=TchBYuSAPZ9Te7lyGXvyktqeNLTjoFy5
REDIS_TLS=true
```

### ❌ 所有测试都失败

**结论**: 代码问题，需要检查 Worker 代码。

**排查步骤**:
1. 查看详细错误输出（使用 `--verbose`）
2. 检查依赖是否安装：
   ```powershell
   pip install upstash-redis python-dotenv requests
   ```
3. 运行单元测试：
   ```powershell
   python python_worker/test_qwen_worker_v2.py
   ```

## 🔧 切换模式

### 切换到内存模式

**方法 1: 修改 .env 文件**
```env
# 在 python_worker/.env 中添加
USE_MEMORY_REDIS=true
```

**方法 2: 环境变量**
```powershell
$env:USE_MEMORY_REDIS="true"
python -m python_worker.agents.qwen.qwen_worker_v2
```

### 切换回云 Redis

**方法 1: 修改 .env 文件**
```env
# 在 python_worker/.env 中删除或注释
# USE_MEMORY_REDIS=true
```

**方法 2: 环境变量**
```powershell
$env:USE_MEMORY_REDIS="false"
python -m python_worker.agents.qwen.qwen_worker_v2
```

## 🎯 诊断流程

```
开始
  ↓
运行测试脚本
  ↓
云 Redis 成功？ ──── 是 ───→ ✅ 直接使用云 Redis
  ↓ 否
内存模式成功？ ──── 是 ───→ ⚠️ 网络问题，配置代理或使用内存模式
  ↓ 否
❌ 代码问题，检查错误日志
```

## 📝 常用命令

```powershell
# 诊断测试
python python_worker/test_qwen_worker_v2_redis.py                    # 云 Redis
python python_worker/test_qwen_worker_v2_redis.py --use-memory       # 内存模式
python python_worker/test_qwen_worker_v2_redis.py --verbose          # 详细日志

# 启动 Worker
python -m python_worker.agents.qwen.qwen_worker_v2                   # 默认模式
USE_MEMORY_REDIS=true python -m python_worker.agents.qwen.qwen_worker_v2  # 内存模式

# 检查配置
cat python_worker/.env | Select-String "REDIS"
```

## 💡 提示

1. **内存模式仅用于调试**，生产环境请使用云 Redis
2. **内存模式重启后数据丢失**，不要用于持久化任务
3. **云 Redis 更稳定**，建议解决网络问题后使用
4. **查看详细日志** 有助于定位问题：`--verbose`

## 🆘 常见问题

### Q: 如何知道当前使用的是哪种模式？

**A**: 查看 Worker 启动时的输出：
```
⚠️  使用内存模式（绕过云 Redis）  ← 内存模式
```
如果没有这条消息，说明使用的是云 Redis。

### Q: 内存模式会影响功能吗？

**A**: 
- ✅ 功能完全一致
- ❌ 不支持分布式（多 Worker）
- ⚠️ 重启后数据丢失

### Q: 为什么云 Redis 会超时？

**A**: 可能原因：
1. 网络连接不稳定
2. 需要配置代理
3. 防火墙阻止
4. DNS 解析问题

**解决**: 使用 `--verbose` 查看详细错误信息。

### Q: 如何验证修复是否成功？

**A**: 
```powershell
# 重新运行测试
python python_worker/test_qwen_worker_v2_redis.py

# 如果全部通过，启动 Worker
python -m python_worker.agents.qwen.qwen_worker_v2
```

## 📚 相关文档

- [完整诊断指南](REDIS_DEBUG_GUIDE.md)
- [测试脚本源码](test_qwen_worker_v2_redis.py)
- [Worker 配置](worker_config.py)

---

**祝调试顺利！** ✨
