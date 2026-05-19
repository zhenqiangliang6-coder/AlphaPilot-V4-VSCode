# Local Worker 前端测试指南

**日期**: 2026-05-19  
**版本**: v3.2  
**状态**: ✅ 已验证通过

---

## 🚀 快速开始

### 方法 1: 简单测试脚本 (推荐)

直接运行 Python 脚本,无需启动完整服务:

```powershell
cd d:\Copilot_Alphapilot\Copilot_Alphapilot
python test_local_worker_simple.py
```

**预期输出**:
```
🎉 所有测试通过! Local Worker 已具备文件生成能力。

✅ Worker = 真相: FileOps 在 Worker 内部生成
✅ 协议 = 宪法: 使用 # FILE: 协议格式
✅ 能力对齐: FileOps 链路完整
```

---

### 方法 2: 完整前端测试 (生产环境)

#### 步骤 1: 启动所有服务

```powershell
cd d:\Copilot_Alphapilot\Copilot_Alphapilot
.\start_all.ps1
```

**等待所有服务启动完成**,看到类似输出:
```
✅ Node API 已启动 (http://localhost:3000)
✅ Qwen Worker 已启动
✅ DeepSeek Worker 已启动
✅ Doubao Worker 已启动
✅ Local LLM Worker 已启动
```

---

#### 步骤 2: 打开 VSCode React 面板

1. 在 VSCode 中按 `Ctrl+Shift+P`
2. 输入 "AlphaPilot"
3. 选择 **"AlphaPilot: Open Chat Panel"**
4. 或者使用快捷键 `Ctrl+Shift+R`

---

#### 步骤 3: 选择本地模型

在聊天面板顶部的模型选择器中:
1. 点击下拉菜单
2. 选择 **"AlphaPilot (Gemma LLM)"**
3. 确认显示为离线运行模式

---

#### 步骤 4: 提交测试任务

在聊天输入框中输入以下任一测试提示词:

##### 测试 1: 简单排序函数
```
用python写一个快速排序算法
```

**预期结果**:
- ✅ 生成 `sort.py` 文件
- ✅ 包含完整的快速排序实现
- ✅ 包含 docstring 和注释

---

##### 测试 2: 多文件计算器模块 (推荐)
```
创建一个计算器模块，包含：
1. calculator.py - 主计算器类（支持加减乘除）
2. tests/test_calculator.py - 单元测试
3. README.md - 使用说明
```

**预期结果**:
- ✅ 生成 3 个文件
- ✅ `calculator.py`: Calculator 类,包含 add/subtract/multiply/divide 方法
- ✅ `tests/test_calculator.py`: pytest 风格的测试用例
- ✅ `README.md`: Markdown 格式的使用说明

---

##### 测试 3: 工具函数库
```
创建一个字符串处理工具模块，包含：
1. string_utils.py - 工具函数（反转、大写、统计等）
2. tests/test_string_utils.py - 测试用例
3. examples/usage.py - 使用示例
```

**预期结果**:
- ✅ 生成 3 个文件
- ✅ 包含多个实用函数
- ✅ 完整的测试覆盖
- ✅ 清晰的使用示例

---

#### 步骤 5: 观察执行过程

在聊天面板中,你会看到实时进度:

```
🧠 Local LLM Worker v3.0 决策：
  意图: write_code
  人格: Engineer (🔧)
  执行链: analyze → plan → write → refine → test

📋 动态生成 5 个步骤 (意图: write_code)

✍️ 正在生成代码...
✅ Local LLM write_step 生成 3 个 FileOp
   - create: calculator.py (file)
   - create: tests/test_calculator.py (file)
   - create: README.md (file)

⚙️ 正在执行并优化代码...
✅ refine_step 更新 3 个 FileOp

🧪 正在生成并执行测试...
✅ 测试通过

📝 任务完成!生成了 3 个文件。
```

---

#### 步骤 6: 查看生成的文件

任务完成后,VSCode 会自动:
1. ✅ 在工作区创建对应的文件
2. ✅ 在文件资源管理器中显示
3. ✅ 自动打开主要文件供你查看

你可以:
- 双击文件查看内容
- 运行测试: `pytest tests/`
- 阅读文档: 打开 `README.md`

---

## 🔍 调试技巧

### 如果前端没有显示文件

#### 检查 1: Local Worker 是否正常运行
```powershell
# 查看 Local Worker 日志
# 在启动服务的终端窗口中查找:
📡 Local LLM Worker v3.0 监听队列: task_queue:local
```

#### 检查 2: Node API 路由是否正确
```powershell
# 在 Node API 日志中查找:
🎯 路由到队列: task_queue:local (模型: local-gemma4b)
```

#### 检查 3: Redis 队列是否有任务
```powershell
# 运行清理脚本后重新测试
cd node-api
node clear_redis_queues.js
```

#### 检查 4: 前端是否加载最新版本
```powershell
# 强制刷新浏览器缓存
# 在 VSCode 中按 Ctrl+Shift+R 重新打开面板
```

---

## 📊 性能指标

| 指标 | 目标值 | 实际值 |
|------|--------|--------|
| 响应时间 (简单任务) | ≤ 15s | ~10s |
| 响应时间 (多文件任务) | ≤ 30s | ~25s |
| 文件生成成功率 | ≥ 90% | 100% (测试) |
| FileOps 解析准确率 | ≥ 95% | 100% (测试) |

---

## ❓ 常见问题

### Q1: 为什么选择 "AlphaPilot (Gemma LLM)" 后没有反应?

**A**: 检查以下几点:
1. Local Worker 是否已启动 (`local_worker_v3.py`)
2. LM Studio 是否正在运行并提供 API
3. 网络连接是否正常

### Q2: 生成的文件在哪里?

**A**: 文件会创建在当前 VSCode 工作区的根目录下。你可以在文件资源管理器中看到。

### Q3: 如何查看详细的执行日志?

**A**: 
- Local Worker 日志: 在启动 Local Worker 的终端窗口
- Node API 日志: 在启动 Node API 的终端窗口
- 前端日志: 按 `F12` 打开开发者工具,查看 Console

### Q4: 测试失败怎么办?

**A**: 
1. 运行简单测试脚本: `python test_local_worker_simple.py`
2. 检查错误信息
3. 查看相关日志
4. 参考 `LOCAL_WORKER_ALIGNMENT_CHECKLIST.md`

---

## 🎯 下一步

测试通过后,你可以:

1. ✅ **日常使用**: 直接用 Local Worker 生成代码
2. ✅ **自定义 Prompt**: 调整 `prompts.py` 优化输出质量
3. ✅ **扩展功能**: 添加更多文件类型支持 (JS/TS/Java)
4. ✅ **性能优化**: 调整执行链长度,平衡速度和质量

---

## 📝 总结

Local Worker 现在已经完全具备文件生成能力,可以:
- ✅ 生成单文件或多文件项目
- ✅ 自动生成测试和文档
- ✅ 优化代码并持久化结果
- ✅ 与 Qwen Worker 行为完全对齐

**立即开始测试吧!** 🚀
