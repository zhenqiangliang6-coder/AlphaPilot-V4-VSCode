# -*- coding: utf-8 -*-
# deepseek_worker.py
# ---------------------------------------------------------
# DeepSeek 专用 Worker（逐 token / reasoning 流式）
# ---------------------------------------------------------

import os
import json
import time
import traceback
import requests
from dotenv import load_dotenv
from upstash_redis import Redis
from task_model import TaskModel, pretty_print

load_dotenv()

redis = Redis(
    url=os.getenv("UPSTASH_REDIS_REST_URL"),
    token=os.getenv("UPSTASH_REDIS_REST_TOKEN")
)

NODE_API_URL = os.getenv("NODE_API_URL", "http://localhost:3000")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

WORKER_ID = os.getenv("WORKER_ID", "deepseek-worker-1")
TASK_MODEL_VERSION = "1.0"

MAX_RETRIES = 3
RETRY_DELAY = 1  # 秒

print(f"\n🚀 DeepSeek Worker 已启动")
print(f"   · Worker ID: {WORKER_ID}")
print(f"   · Node API: {NODE_API_URL}")
print(f"   · 任务格式版本: {TASK_MODEL_VERSION}")
print(f"   · 最大重试次数: {MAX_RETRIES}")
print(f"\n📻 等待任务...\n")


def stream_start(task_id: str, title: str = "DeepSeek 正在推理..."):
    try:
        requests.post(
            f"{NODE_API_URL}/task/stream_start/{task_id}",
            json={"task_id": task_id, "title": title},
            timeout=5,
        )
    except Exception as e:
        print(f"⚠️ stream_start 失败：{e}")


def stream_chunk(task_id: str, content: str):
    try:
        requests.post(
            f"{NODE_API_URL}/task/stream_chunk/{task_id}",
            json={"task_id": task_id, "content": content},
            timeout=5,
        )
    except Exception as e:
        print(f"⚠️ stream_chunk 失败：{e}")


def stream_error(task_id: str, message: str):
    try:
        requests.post(
            f"{NODE_API_URL}/task/stream_error/{task_id}",
            json={"task_id": task_id, "message": message},
            timeout=5,
        )
    except Exception as e:
        print(f"⚠️ stream_error 失败：{e}")


def stream_end(task_id: str):
    try:
        requests.post(
            f"{NODE_API_URL}/task/stream_end/{task_id}",
            json={"task_id": task_id},
            timeout=5,
        )
    except Exception as e:
        print(f"⚠️ stream_end 失败：{e}")


# =========================
# ⭐ DeepSeek 专用 Parser
# =========================

def parse_deepseek_stream(response, task_id: str) -> str:
    """
    解析 DeepSeek 的流式响应：
    - SSE data: {...}
    - choices[0].delta.content 为可见内容
    - 如果有 reasoning_content，可选择单独处理
    """
    full_text = ""

    for raw_line in response.iter_lines():
        if not raw_line:
            continue

        line = raw_line.decode("utf-8")
        if not line.strip() or not line.lstrip().startswith("data:"):
            continue

        data_str = line[line.find("data:") + len("data:"):]
        data_str = data_str.strip("\r\n")
        if data_str == "[DONE]":
            break

        try:
            data = json.loads(data_str)
        except Exception:
            continue

        choices = data.get("choices") or []
        if not choices:
            continue

        delta = choices[0].get("delta", {})

        # reasoning_content（可选：你可以选择单独展示）
        reasoning = delta.get("reasoning_content") or ""
        if reasoning:
            stream_chunk(task_id, f"[reasoning] {reasoning}")

        content = delta.get("content") or ""
        if not content or not content.strip():
            continue

        full_text += content
        stream_chunk(task_id, content)

    return full_text


# =========================
# 任务执行逻辑
# =========================

def execute_deepseek_generate(task_id: str, payload: dict) -> str:
    """
    执行 deepseek_generate 任务
    """
    if not DEEPSEEK_API_KEY:
        raise Exception("DEEPSEEK_API_KEY 未设置")

    prompt = payload.get("prompt")
    if not prompt:
        raise ValueError("prompt 不能为空")

    stream_start(task_id, title="DeepSeek 正在推理...")

    url = "https://api.deepseek.com/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": payload.get("model") or "deepseek-chat",
        "stream": True,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }

    try:
        with requests.post(url, headers=headers, json=body, stream=True) as r:
            r.raise_for_status()
            full_text = parse_deepseek_stream(r, task_id)
    except Exception as exc:
        err_msg = str(exc)
        stream_error(task_id, err_msg)
        stream_chunk(task_id, f"[ERROR] {err_msg}\n")
        stream_end(task_id)
        raise

    stream_end(task_id)
    return full_text


def execute_task(task_type: str, payload: dict, task_id: str):
    if task_type == "deepseek_generate":
        return execute_deepseek_generate(task_id, payload)

    elif task_type == "add_numbers":
        a = payload.get("a")
        b = payload.get("b")
        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
            raise TypeError(f"参数必须是数字，收到: a={type(a).__name__}, b={type(b).__name__}")
        return a - b

    else:
        raise ValueError(f"未知任务类型: {task_type}")


# =========================
# 主循环
# =========================

def main_loop():
    while True:
        try:
            task_json = redis.rpop("task_queue")

            if not task_json:
                time.sleep(1)
                continue

            task = json.loads(task_json)
            print("📥 [DeepSeek] 收到任务（标准格式）：")
            print(pretty_print(task))

            task_id = task.get("task_id")
            task_type = task.get("type", "unknown")
            payload = task.get("payload", {})
            started_at = int(time.time() * 1000)

            result_value = None
            last_error = None
            last_error_code = None
            last_error_stack = None
            success = False

            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    print(f"\n🔄 [DeepSeek] 尝试执行任务 (第 {attempt}/{MAX_RETRIES} 次)...")
                    result_value = execute_task(task_type, payload, task_id)
                    success = True
                    print(f"✅ 第 {attempt} 次尝试成功，结果: {result_value}")
                    break
                except Exception as e:
                    last_error = str(e)
                    last_error_code = type(e).__name__
                    last_error_stack = traceback.format_exc()
                    print(f"❌ 第 {attempt} 次尝试失败：{last_error}")

                    if attempt < MAX_RETRIES:
                        print(f"⏳ 等待 {RETRY_DELAY} 秒后重试...")
                        time.sleep(RETRY_DELAY)
                    else:
                        print(f"❌ 已达到最大重试次数 ({MAX_RETRIES})，准备推送失败结果")

            if success:
                result_obj = TaskModel.create_task_result_success(
                    task_id=task_id,
                    task_type=task_type,
                    result={"value": result_value},
                    worker_id=WORKER_ID,
                    started_at=started_at
                )

                redis.set(f"task_result:{task_id}", json.dumps(result_obj))
                print("\n📤 已写回 Redis（标准格式）：")
                print(f"Key: task_result:{task_id}")
                print(pretty_print(result_obj))

                try:
                    notify_url = f"{NODE_API_URL}/task/notify/{task_id}"
                    print(f"\n📡 通知 Node API（标准格式）：POST {notify_url}")
                    resp = requests.post(notify_url, json=result_obj, timeout=5)
                    if resp.status_code == 200:
                        print("✅ 标准格式结果已推送")
                    else:
                        print(f"⚠️ 推送失败，HTTP 状态码：{resp.status_code}")
                except Exception as notify_err:
                    print(f"⚠️ 无法通知 Node API：{notify_err}")

                print("\n" + "=" * 50 + "\n")

            else:
                error_result = TaskModel.create_task_result_error(
                    task_id=task_id,
                    task_type=task_type,
                    error_message=last_error,
                    worker_id=WORKER_ID,
                    error_code=last_error_code,
                    error_stack=last_error_stack,
                    retryable=True,
                    started_at=started_at,
                    retry_count=MAX_RETRIES
                )

                redis.set(f"task_result:{task_id}", json.dumps(error_result))
                print("\n📤 已写入失败结果到 Redis（标准格式）：")
                print(pretty_print(error_result))

                dlq_item = TaskModel.create_dlq_item(
                    original_task=task,
                    failure_record=error_result["error"],
                    retry_count=MAX_RETRIES,
                    first_failed_at=started_at
                )
                redis.lpush("dlq", json.dumps(dlq_item))
                print("\n💀 写入 DLQ（标准格式）：")
                print(pretty_print(dlq_item))

                try:
                    notify_url = f"{NODE_API_URL}/task/notify/{task_id}"
                    print(f"\n📡 通知 Node API 任务失败（标准格式）：POST {notify_url}")
                    resp = requests.post(notify_url, json=error_result, timeout=5)
                    if resp.status_code == 200:
                        print("✅ 标准格式失败通知已发送")
                    else:
                        print(f"⚠️ 推送失败通知失败，HTTP 状态码：{resp.status_code}")
                except Exception as notify_err:
                    print(f"⚠️ 无法通知 Node API：{notify_err}")

                print("\n" + "=" * 50 + "\n")

        except Exception as e:
            print(f"❌ DeepSeek Worker 发生未预期的错误：{e}")
            print(traceback.format_exc())
            time.sleep(1)


if __name__ == "__main__":
    main_loop()
