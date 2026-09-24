import os, json, time
from dotenv import load_dotenv
load_dotenv()
from upstash_redis import Redis

redis = Redis(url=os.getenv('UPSTASH_REDIS_REST_URL'), token=os.getenv('UPSTASH_REDIS_REST_TOKEN'))

task_id = f"manual_{int(time.time())}"
queue = 'task_queue:qwen'

task = {
    'task_id': task_id,
    'task_type': 'qwen_generate',
    'payload': {'prompt': '请生成一个简单的 Python 函数，实现两个数相加并返回结果。'},
    'steps': [],
    'events': [],
    'context': {}
}

print('Pushing task:', task_id)
redis.lpush(queue, json.dumps(task))
print('Pushed to', queue)
print('Task id:', task_id)
