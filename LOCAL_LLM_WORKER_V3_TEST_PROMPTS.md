# Local LLM Worker v3.0 测试提示词集合
# =========================================================
# 用途: 用于验证 Local LLM Worker v3.0 的执行链路和 FileOps 生成能力
# 使用方法: 复制任意一个提示词到 VSCode AlphaPilot Chat 输入框
# =========================================================

## 📋 测试场景分类

### 1️⃣ 简单任务测试（验证智能简化执行链）
**预期执行链**: write → test (2步)

---

**测试 1.1: 基础排序函数**
```
写一个 Python 排序函数，支持升序和降序
```

**预期输出**:
- ✅ 意图识别: write_code → simple_code
- ✅ 执行链: write → test
- ✅ 生成文件: main.py
- ✅ FileOps: 1个 create 操作

---

**测试 1.2: 工具函数**
```
实现一个计算斐波那契数列的函数
```

**预期输出**:
- ✅ 意图识别: write_code → simple_code
- ✅ 执行链: write → test
- ✅ 生成文件: main.py

---

### 2️⃣ 中等任务测试（验证完整执行链）
**预期执行链**: analyze → plan → write → refine → test → fix → doc → docstring (8步)

---

**测试 2.1: 多文件项目**
```
创建一个 Python 项目，包含以下文件：
1. hello.py - 打印问候语的函数
2. utils.py - 字符串处理工具函数
3. main.py - 主程序入口
4. tests/test_hello_utils_main.py - 单元测试
5. docs/README.md - 项目文档

要求：
- 每个文件都要有完整的 docstring
- 使用 pytest 风格测试
- 遵循 PEP 8 规范
```

**预期输出**:
- ✅ 意图识别: write_code
- ✅ 执行链: 完整 8 步链
- ✅ 生成文件: 5个文件
- ✅ FileOps: 5个 create 操作（包含 FILE/TEST/DOC/META/DEPENDS 协议）

---

**测试 2.2: Web 应用**
```
创建一个简单的 Flask Web 应用，包含：
1. app.py - Flask 应用主文件
2. routes.py - 路由定义
3. templates/index.html - 首页模板
4. static/style.css - 样式文件
5. requirements.txt - 依赖列表

功能要求：
- 首页显示 "Hello, World!"
- 支持 /about 路由
- 使用 Jinja2 模板引擎
```

**预期输出**:
- ✅ 意图识别: write_code
- ✅ 执行链: 完整 8 步链
- ✅ 生成文件: 5个文件
- ✅ FileOps: 5个 create 操作

---

### 3️⃣ 复杂任务测试（验证多文件协议解析）
**预期执行链**: analyze → plan → write → refine → test → fix → doc → docstring (8步)

---

**测试 3.1: 数据结构项目**
```
创建一个完整的数据结构库项目，包含：

# FILE: linked_list.py
实现链表数据结构，支持插入、删除、查找操作

# FILE: stack.py
实现栈数据结构，基于链表

# FILE: queue.py
实现队列数据结构，基于链表

# TEST: tests/test_data_structures.py
为所有数据结构编写单元测试

# DOC: docs/API_REFERENCE.md
生成 API 参考文档

要求：
- 每个类和方法都要有完整的 docstring
- 测试覆盖率 > 80%
- 遵循 SOLID 原则
```

**预期输出**:
- ✅ 意图识别: write_code
- ✅ 执行链: 完整 8 步链
- ✅ 生成文件: 5个文件（严格按照 # FILE: 协议）
- ✅ FileOps: 5个 create 操作，包含明确的 FILE/TEST/DOC 标记

---

**测试 3.2: REST API 服务**
```
创建一个 REST API 服务项目：

# FILE: app.py
Flask 应用主文件，配置路由和中间件

# FILE: models/user.py
用户数据模型

# FILE: routes/users.py
用户相关 API 路由（CRUD）

# FILE: config.py
应用配置文件

# TEST: tests/test_users_api.py
API 接口测试

# DOC: docs/GETTING_STARTED.md
快速开始指南

# META: {"version": "1.0.0", "author": "AlphaPilot"}

功能要求：
- 支持用户注册、登录、查询、更新、删除
- 使用 JWT 认证
- 返回标准 JSON 格式
- 包含错误处理
```

**预期输出**:
- ✅ 意图识别: write_code
- ✅ 执行链: 完整 8 步链
- ✅ 生成文件: 6个文件 + META 信息
- ✅ FileOps: 6个 create 操作，包含 META 元数据

---

### 4️⃣ 特殊意图测试

---

**测试 4.1: 代码解释**
```
解释以下 Python 代码的工作原理：

def quicksort(arr):
    if len(arr) <= 1:
        return arr
    pivot = arr[len(arr) // 2]
    left = [x for x in arr if x < pivot]
    middle = [x for x in arr if x == pivot]
    right = [x for x in arr if x > pivot]
    return quicksort(left) + middle + quicksort(right)
```

**预期输出**:
- ✅ 意图识别: explain_code
- ✅ 执行链: analyze → plan → doc (3步)
- ✅ 生成详细的代码解释文档

---

**测试 4.2: 创意写作**
```
写一首关于编程的诗歌，主题是"代码与艺术"
```

**预期输出**:
- ✅ 意图识别: creative_writing
- ✅ 执行链: analyze → plan → write → refine (4步)
- ✅ 生成富有诗意的内容

---

**测试 4.3: 闲聊对话**
```
你好！今天过得怎么样？
```

**预期输出**:
- ✅ 意图识别: chat
- ✅ 执行链: analyze → write (2步)
- ✅ 生成友好自然的回复

---

### 5️⃣ 边界情况测试

---

**测试 5.1: 空输入**
```

```

**预期输出**:
- ⚠️ Worker 应该拒绝空输入并返回错误提示

---

**测试 5.2: 超长提示词**
```
[粘贴一段超过 1000 字的详细需求描述...]
```

**预期输出**:
- ✅ 意图识别: write_code
- ✅ 执行链: 完整 8 步链
- ✅ 正确处理长文本

---

**测试 5.3: 多语言混合**
```
Write a Python function to calculate factorial, and add Chinese comments explaining the logic.
```

**预期输出**:
- ✅ 意图识别: write_code
- ✅ 生成带中文注释的代码

---

## 🎯 推荐测试顺序

### 快速验证（5分钟）
1. **测试 1.1**: 基础排序函数 → 验证智能简化执行链
2. **测试 2.1**: 多文件项目 → 验证完整执行链和 FileOps 生成

### 完整验证（15分钟）
3. **测试 3.1**: 数据结构项目 → 验证多文件协议解析
4. **测试 3.2**: REST API 服务 → 验证 META 元数据支持
5. **测试 4.1**: 代码解释 → 验证不同意图类型

### 压力测试（可选）
6. **测试 5.2**: 超长提示词 → 验证鲁棒性
7. **测试 5.3**: 多语言混合 → 验证国际化支持

---

## 📊 验证检查清单

在每个测试完成后，检查以下项目：

### Worker 日志验证
- [ ] 看到 `🧠 Local LLM Worker v3.0 决策：`
- [ ] 看到正确的意图识别结果
- [ ] 看到正确的执行链
- [ ] 看到 `✅ Local LLM write_step 生成 X 个 FileOp`
- [ ] 看到每个 FileOp 的详细信息（action, path, type）
- [ ] 看到 `📡 正在通知 Node.js: ...`
- [ ] 看到 `✅ Node.js 已成功接收通知`

### 前端验证
- [ ] 流式输出正常显示（不是一次性显示）
- [ ] 看到步骤进度（分析、计划、生成、测试等）
- [ ] FileOps 面板出现文件操作列表
- [ ] 点击"应用"后文件正确写入磁盘
- [ ] 在 VSCode 中能看到生成的文件

### 文件系统验证
- [ ] 文件路径正确（相对路径，无绝对路径）
- [ ] 文件内容符合预期
- [ ] 目录结构正确创建
- [ ] 文件编码正确（UTF-8）

---

## 💡 调试技巧

### 如果流式输出不工作
1. 检查 Worker 日志是否有 `[WARN] stream_start 失败` 警告
2. 确认 execute_step 调用了 `handler(step, context, events, task_id=task_id)`
3. 检查所有步骤函数是否都有 `task_id=None` 参数

### 如果 FileOps 未生成
1. 检查 Worker 日志是否有 `[ERROR] Local LLM 解析 FileOps 失败`
2. 确认 LLM 输出了正确的 `# FILE:` 标记
3. 查看 write_step 的输出，确认 result 包含多文件协议格式

### 如果任务卡住
1. 检查 Redis 队列是否有积压任务
2. 检查 Worker 是否在运行
3. 查看 Worker 日志最后的输出

---

## 🚀 开始测试

**建议从测试 1.1 开始**，逐步增加复杂度。每个测试都应该能看到：
1. ✅ Worker 日志中的完整执行链路
2. ✅ 前端的流式输出
3. ✅ FileOps 面板的文件操作列表
4. ✅ 最终生成的文件

**祝测试顺利！如果遇到问题，随时告诉我！** 🎉
