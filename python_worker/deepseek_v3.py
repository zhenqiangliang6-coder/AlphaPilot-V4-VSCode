import requests
import json
import sys
import os
from dotenv import load_dotenv

# 1. 加载配置
load_dotenv()

# 优先读取专用 Key，如果没有则读取通用 Key
API_KEY = os.getenv("VOLC_DEEPSEEK_API_KEY") or os.getenv("VOLC_API_KEY")
MODEL_NAME = os.getenv("VOLC_DEEPSEEK_MODEL", "deepseek-v3-250324")

# 🛑 关键修改：切换到标准的 Chat Completions API
# 大多数 DeepSeek 模型在火山引擎上都支持这个端点
URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"

if not API_KEY:
    print("❌ 错误：未找到 API Key (请检查 .env 文件)")
    sys.exit(1)

print(f"🚀 启动 Worker: {os.getenv('HOSTNAME', 'Unknown')}")
print(f"🎯 模型：{MODEL_NAME}")
print(f"📡 端点：{URL} (Standard Chat API)")
print("-" * 40)

# 2. 构建请求 (标准 Chat API 格式)
headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

user_prompt = "当我们想按照自己的需求，如何 创建 一个 适合 需求 的 SQL 查询。"

# ✅ 关键修改：使用 messages 列表，而不是 input
payload = {
    "model": MODEL_NAME,
    "stream": True,
    "messages": [
        {
            "role": "user",
            "content": user_prompt
        }
    ]
}

print(f"🤖 AI 开始创作:\n")

try:
    # 3. 发送请求
    with requests.post(URL, headers=headers, json=payload, stream=True, timeout=60) as r:
        if r.status_code != 200:
            print(f"\n❌ 请求失败: {r.status_code}")
            print(f"📄 错误详情: {r.text}")
            sys.exit(1)

        # 处理流式响应 (Chat API 的标准格式)
        for line in r.iter_lines():
            if not line:
                continue
            
            decoded = line.decode('utf-8')
            
            if decoded.startswith("data: "):
                data_str = decoded[6:]
                if data_str.strip() == "[DONE]":
                    break
                
                try:
                    data = json.loads(data_str)
                    
                    # Chat API 的标准提取路径: choices[0].delta.content
                    choices = data.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            print(content, end="", flush=True)
                            
                except json.JSONDecodeError:
                    continue

        print("\n\n" + "-" * 40)
        print("✅ 创作完成")

except Exception as e:
    print(f"\n❌ 发生错误: {e}")
    import traceback
    traceback.print_exc()