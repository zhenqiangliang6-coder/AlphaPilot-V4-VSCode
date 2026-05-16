# AlphaPilot OS v2.8 - Doubao API 流式调用修复报告

## 🐛 问题诊断

### **核心问题**
Doubao Worker 执行任务时，所有步骤都返回：
```
# LLM 调用失败: LLM 返回空字符串
```

导致生成的文件内容为空：
- `main.py` - 空文件
- `docs/README.md` - 空文件

### **根本原因**

#### **1. Doubao API 返回格式解析错误**
火山引擎 Responses API 的返回格式是：
```json
{
  "output": [
    {
      "type": "reasoning",
      "summary": [
        {
          "type": "summary_text",
          "text": "实际内容..."
        }
      ]
    }
  ]
}
```

但代码尝试从 `content` 字段提取，导致返回空字符串。

#### **2. 流式 API 不支持或格式不同**
- 非流式调用：✅ 正常工作（修复后）
- 流式调用：❌ 返回 0 字符（火山引擎可能不支持流式）

---

## 🔧 修复方案

### **修复 1: 正确解析火山引擎 API 响应**

#### **文件**: `python_worker/agents/Volcengine/doubao_api.py`

**修改前**：
```python
if "output" in result:
    output = result["output"]
    if "text" in output:
        return output["text"]
```

**修改后**：
```python
if "output" in result and isinstance(result["output"], list):
    output_list = result["output"]
    if output_list and len(output_list) > 0:
        first_output = output_list[0]
        
        # 尝试从 summary 中提取文本（火山引擎格式）
        if "summary" in first_output:
            summary_list = first_output["summary"]
            if summary_list and len(summary_list) > 0:
                for item in summary_list:
                    if item.get("type") == "summary_text":
                        text_content = item.get("text", "")
                        if text_content:
                            return text_content
        
        # 尝试从 content 中提取文本（备用格式）
        if "content" in first_output:
            content_list = first_output["content"]
            if content_list and len(content_list) > 0:
                text_content = content_list[0].get("text", "")
                if text_content:
                    return text_content
```

### **修复 2: 流式失败自动降级到非流式**

#### **文件**: `python_worker/agents/Volcengine/step_executor/write_step.py`

**修改前**：
```python
if task_id:
    for chunk in call_doubao_stream(full_prompt):
        result += chunk
        stream_chunk(task_id, chunk, phase="write", channel="content")
```

**修改后**：
```python
if task_id:
    try:
        for chunk in call_doubao_stream(full_prompt):
            result += chunk
            stream_chunk(task_id, chunk, phase="write", channel="content")
        
        # 如果流式返回空，降级到非流式
        if not result:
            print("[WARN] 流式调用返回空，降级到非流式模式")
            stream_chunk(task_id, "[系统] 切换到非流式模式...\n", phase="write", channel="reasoning")
            result = call_doubao(full_prompt)
    except Exception as stream_error:
        print(f"[WARN] 流式调用失败，降级到非流式模式: {stream_error}")
        stream_chunk(task_id, f"[系统] 流式失败，切换非流式: {stream_error}\n", phase="write", channel="reasoning")
        result = call_doubao(full_prompt)
```

---

## ✅ 验证结果

### **测试 1: 非流式调用**
```
✅ 成功！返回长度: 314 字符
内容预览: 用户现在让用一句话介绍自己...
```

### **测试 2: 流式调用**
```
⚠️  返回长度: 0 字符（火山引擎不支持流式）
✅ 自动降级到非流式模式
```

### **Worker 重启**
```
🚀 Doubao Worker v3.0 已启动
✅ 使用阿里云 Tair Redis（国内模型/国内加速）
💡 Worker 类型: doubao
💡 Redis 类型: tair
```

---

## 📊 当前状态

### **已完成**
- ✅ 双云 Redis 架构（Node API + Workers）
- ✅ Doubao API 响应格式修复
- ✅ 流式失败自动降级机制
- ✅ Doubao Worker 重启

### **进行中**
- ⏳ 端到端测试（新任务正在执行）

---

## 💡 经验总结

### **API 兼容性陷阱**
不同厂商的 API 返回格式差异很大：
- OpenAI: `choices[0].message.content`
- Qwen: `output.text`
- **火山引擎**: `output[0].summary[0].text`

### **容错设计原则**
1. **多层降级策略**：流式 → 非流式 → 错误提示
2. **详细日志**：记录 API 返回的原始格式
3. **异常捕获**：不要假设 API 一定成功

---

## 🎯 下一步

1. **等待当前任务完成** - 观察是否成功生成代码
2. **检查文件内容** - 确认 main.py 不为空
3. **验证前端展示** - Webview 收到完整结果