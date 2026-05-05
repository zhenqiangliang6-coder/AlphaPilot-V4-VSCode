#!/usr/bin/env python3
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


# import os
# import requests
# from dotenv import load_dotenv

# # 1. 加载环境变量
# load_dotenv()

# # 2. 获取配置
# API_KEY = os.getenv("VOLC_API_KEY")
# BASE_URL = "https://ark.cn-beijing.volces.com/api/v3/responses"
# MODEL_NAME = "doubao-seed-2-0-lite-260215"

# if not API_KEY:
#     print("❌ 错误：未找到 VOLC_API_KEY，请检查 .env 文件")
#     exit(1)

# # 3. 构建请求 payload (和刚才 curl 成功的一样)
# payload = {
#     "model": MODEL_NAME,
#     "input": [
#         {
#             "role": "user",
#             "content": [
#                 {
#                     "type": "input_image",
#                     "image_url": "https://ark-project.tos-cn-beijing.volces.com/doc_image/ark_demo_img_1.png"
#                 },
#                 {
#                     "type": "input_text",
#                     "text": "你看见了什么？请用简短的一句话回答。"
#                 }
#             ]
#         }
#     ]
# }

# headers = {
#     "Authorization": f"Bearer {API_KEY}",
#     "Content-Type": "application/json"
# }

# print(f"🚀 正在调用火山引擎模型 {MODEL_NAME} ...")

# try:
#     # 4. 发送请求
#     response = requests.post(BASE_URL, json=payload, headers=headers)
    
#     # 5. 检查状态码
#     if response.status_code == 200:
#         data = response.json()
        
#         # 提取回答内容
#         # 结构通常是: output -> [0] or [1] -> content -> [0] -> text
#         # 注意：豆包有时会返回 reasoning (思考过程) 和 message (最终回答) 两个部分
#         output_list = data.get("output", [])
        
#         final_answer = ""
#         for item in output_list:
#             if item.get("type") == "message":
#                 content_list = item.get("content", [])
#                 for content_item in content_list:
#                     if content_item.get("type") == "output_text":
#                         final_answer = content_item.get("text")
#                         break
        
#         print("\n✅ 模型回答:")
#         print("-" * 30)
#         print(final_answer)
#         print("-" * 30)
        
#         # 打印 Token 使用情况
#         usage = data.get("usage", {})
#         print(f"💰 消耗 Token: {usage.get('total_tokens', 0)} (输入:{usage.get('input_tokens', 0)}, 输出:{usage.get('output_tokens', 0)})")
        
#     else:
#         print(f"❌ 请求失败: {response.status_code}")
#         print(response.text)

# except Exception as e:
#     print(f"❌ 发生异常: {str(e)}")


# import requests
# import json
# import sys
# import os
# from dotenv import load_dotenv

# # 1. 加载配置
# load_dotenv()
# API_KEY = os.getenv("VOLC_DEEPSEEK_API_KEY")
# MODEL_NAME = os.getenv("VOLC_DEEPSEEK_MODEL", "deepseek-v3-2-251201")
# URL = os.getenv("VOLC_API_URL", "https://ark.cn-beijing.volces.com/api/v3/responses")

# if not API_KEY:
#     print("❌ 错误：未找到 API Key")
#     sys.exit(1)

# print(f"🎯 测试目标：纯文本流式输出 (写一首关于愿景与未来的诗)")
# print("-" * 40)

# # 2. 构建请求 (❌ 去掉 tools，✅ 纯文本)
# headers = {
#     "Authorization": f"Bearer {API_KEY}",
#     "Content-Type": "application/json"
# }

# payload = {
#     "model": MODEL_NAME,
#     "stream": True,
#     # 没有 tools 字段
#     "input": [
#         {
#             "role": "user",
#             "content": [
#                 {
#                     "type": "input_text",
#                     "text": "请写一首关于愿景与未来的现代诗，要求意境优美，充满希望。直接输出诗歌内容，不要多余的解释。"
#                 }
#             ]
#         }
#     ]
# }

# print("🤖 AI 开始创作:\n")

# try:
#     # 3. 发送请求
#     with requests.post(URL, headers=headers, json=payload, stream=True, timeout=60) as r:
#         if r.status_code != 200:
#             print(f"\n❌ 请求失败: {r.status_code} - {r.text}")
#             sys.exit(1)

#         current_event = None
        
#         for line in r.iter_lines():
#             if not line:
#                 continue
            
#             decoded = line.decode('utf-8')
            
#             # 识别事件行
#             if decoded.startswith("event: "):
#                 current_event = decoded.split("event: ")[1].strip()
#                 continue
            
#             # 处理数据行
#             if decoded.startswith("data: "):
#                 data_str = decoded[6:]
#                 if data_str.strip() == "[DONE]":
#                     break
                
#                 try:
#                     data = json.loads(data_str)
                    
#                     # 🔑 核心逻辑：只在特定事件下提取 delta
#                     if current_event == "response.output_text.delta":
#                         chunk = data.get("delta", "")
#                         if chunk:
#                             print(chunk, end="", flush=True)
                    
#                     # 备用逻辑：防止某些版本把文字放在 text 字段里
#                     elif current_event == "response.content_part.done" or current_event == "response.output_text.done":
#                         # 有些实现会在 done 事件里返回完整文本，以防万一检查一下
#                         full_text = data.get("text", "")
#                         if full_text and not hasattr(sys, '_text_printed'): 
#                             # 这里只是做个兜底，正常流式不应该走这里
#                             pass

#                 except json.JSONDecodeError:
#                     continue

#         print("\n\n" + "-" * 40)
#         print("✅ 创作完成")

# except Exception as e:
#     print(f"\n❌ 发生错误: {e}")
#     import traceback
#     traceback.print_exc()




import requests
import json
import time
import sys

# ==========================================
# 1. 配置中心
# ==========================================
API_KEY = "4ab0723a-e83a-469e-adbc-9ffdc0995b7b"
# ✅ 已更新为测试通过的模型 ID
MODEL_NAME = "deepseek-v3-250324" 
URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
# BASE_URL = "https://ark.cn-beijing.volces.com/api/v3/responses"

print(f"🚀 启动自主联网分布式节点 (模型：{MODEL_NAME})...")
print(f"📡 接口地址：{URL}\n")

# ==========================================
# 2. 模拟联网搜索工具 (Mock Search)
# ==========================================
# 在真实场景中，这里可以替换为调用 Bing API, Google Serper, 或 Tavily API
def perform_web_search(query):
    print(f"\n🔍 [系统] 正在执行自主联网搜索：'{query}' ...")
    time.sleep(1.5) # 模拟网络延迟
    
    # 模拟返回的搜索结果
    return f"""
    [搜索结果摘要 - {time.strftime('%Y-%m-%d')}]
    1. 关于"{query}"的最新报道显示，技术进展迅速。
    2. 市场分析师指出，该领域将在未来几个月内迎来爆发。
    3. 相关开源项目 GitHub Star 数今日增长显著。
    """

# ==========================================
# 3. 主逻辑循环
# ==========================================
def run_agent():
    # 初始对话
    messages = [
        {"role": "system", "content": "你是一个智能助手。当用户询问新闻、天气、实时数据或你不知道的最新信息时，请务必调用 'web_search' 工具获取最新信息，不要编造。"},
        {"role": "user", "content": "今天有什么关于中国A股指数收盘是涨还是跌了，今天的日期是几号？请总结三条。"}
    ]

    # 定义工具 Schema
    tools_definition = [
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "搜索互联网上的实时新闻、天气、股票价格或最新事件。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索关键词，例如 'AI 最新新闻' 或 '北京天气'"}
                    },
                    "required": ["query"]
                }
            }
        }
    ]

    max_turns = 5 # 防止死循环
    turn = 0

    while turn < max_turns:
        turn += 1
        print(f"\n--- 第 {turn} 轮交互 ---")
        
        payload = {
            "model": MODEL_NAME,
            "messages": messages,
            "tools": tools_definition,
            "tool_choice": "auto", # 让模型自动决定是否调用工具
            "stream": False
        }
        
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }
        
        try:
            print("⏳ 正在请求模型...")
            resp = requests.post(URL, headers=headers, json=payload, timeout=60)
            resp.raise_for_status() # 检查 HTTP 错误
            data = resp.json()
            
            choice = data['choices'][0]
            message = choice['message']
            
            # --- 情况 A: 模型直接回答 (没有调用工具) ---
            if message.get('content'):
                print(f"\n🤖 AI 回复:\n{message['content']}")
                print("\n✅ 任务完成，退出循环。")
                break
            
            # --- 情况 B: 模型请求调用工具 ---
            if message.get('tool_calls'):
                tool_call = message['tool_calls'][0] # 取第一个工具调用
                func_name = tool_call['function']['name']
                func_args = json.loads(tool_call['function']['arguments'])
                tool_call_id = tool_call['id']
                
                print(f"\n⚙️ 模型触发工具: {func_name}")
                print(f"   参数: {func_args}")
                
                # 将模型的请求加入历史
                messages.append(message)
                
                # 执行对应的本地函数
                if func_name == "web_search":
                    search_result = perform_web_search(func_args['query'])
                    
                    # 将搜索结果反馈给模型
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": search_result
                    })
                    print("✅ 搜索结果已注入上下文，准备生成最终回答...\n")
                    # 继续循环，让模型根据搜索结果生成回答
                    continue
                else:
                    print(f"❌ 未知工具: {func_name}")
                    break

        except requests.exceptions.HTTPError as e:
            print(f"\n❌ HTTP 错误: {e}")
            print(f"响应内容: {e.response.text}")
            break
        except Exception as e:
            print(f"\n❌ 发生异常: {e}")
            break

if __name__ == "__main__":
    run_agent()



