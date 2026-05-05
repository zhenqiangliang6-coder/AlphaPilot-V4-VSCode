# !/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
# =============================================================================
# 测试脚本：火山引擎 (Volcengine) 豆包大模型 API 调用
# =============================================================================
# 功能说明：
#     此脚本模拟了 curl 命令，向火山引擎 Ark 平台发送多模态请求（图片 + 文本）。
#     用于测试 API Key 有效性、模型响应速度及内容准确性。

# 前置准备：
#     1. 确保已安装依赖库：pip install requests python-dotenv
#     2. 在项目根目录创建 .env 文件，并填入：VOLC_API_KEY=你的密钥
#     3. 或者直接将下方的 API_KEY 变量硬编码为你的密钥（不推荐用于生产环境）。

# 作者：DavidLiang
# 日期：2026-03-07
# =============================================================================
# """

import os
import json
import requests
from dotenv import load_dotenv

# ---------------- 1. 配置区域 (Configuration) ----------------

# 加载 .env 文件中的环境变量 (如果存在)
load_dotenv()

# 【重要】API 密钥
# 优先从环境变量获取，如果没有则使用默认值（请在此处替换为你有效的 Key）
# 对应 curl 命令中的：-H "Authorization: Bearer ..."
API_KEY = os.getenv("VOLC_API_KEY", "4ab0723a-e83a-469e-adbc-9ffdc0995b7b")

# API 接口地址
# 对应 curl 命令中的 URL
BASE_URL = "https://ark.cn-beijing.volces.com/api/v3/responses"

# 模型名称
# 对应 curl 命令中的 -d "{\"model\": \"...\"}"
MODEL_NAME = "doubao-seed-2-0-lite-260215"

# 测试用的图片 URL
# 你可以修改这里来测试不同的图片
IMAGE_URL = "https://ark-project.tos-cn-beijing.volces.com/doc_image/ark_demo_img_1.png"

# 提示词 (Prompt)
# 对应 curl 命令中的 text 部分
PROMPT_TEXT = "你看见了什么？请用简短的一句话回答。"

import requests
import json

# ==========================================
# 火山引擎 API 测试脚本 (对应 curl 命令)
# ==========================================

# 1. 接口地址 (对应 curl 后面的 URL)
url = "https://ark.cn-beijing.volces.com/api/v3/responses"

# 2. 请求头 (对应 curl 的 -H 参数)
headers = {
    "Authorization": "Bearer 4ab0723a-e83a-469e-adbc-9ffdc0995b7b",
    "Content-Type": "application/json"
}

# 3. 请求数据 (对应 curl 的 -d 参数)
# 这里直接写成了 Python 字典，比 JSON 字符串更好修改
data = {
    "model": "doubao-seed-2-0-lite-260215",
    "input": [
        {
            "role": "user",
            "content": [
                {
                    "type": "input_image",
                    # 👇 想换图片，改这里
                    "image_url": "https://ark-project.tos-cn-beijing.volces.com/doc_image/ark_demo_img_1.png"
                },
                {
                    "type": "input_text",
                    # 👇 想换问题，改这里
                    "text": "你看见了什么？"
                }
            ]
        }
    ]
}

print("正在发送请求...")

# 4. 发送 POST 请求 (对应 curl -X POST)
response = requests.post(url, headers=headers, json=data)

# 5. 打印结果
if response.status_code == 200:
    print("\n✅ 成功！返回内容：")
    # 美化打印 JSON 结果
    result = response.json()
    print(json.dumps(result, indent=2, ensure_ascii=False))
else:
    print(f"\n❌ 失败！状态码: {response.status_code}")
    print(response.text)

