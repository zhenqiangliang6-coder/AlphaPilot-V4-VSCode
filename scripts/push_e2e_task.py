import json, upstash_redis

r = upstash_redis.Redis(
    url='https://growing-cub-282898.upstash.io',
    token='gQAAAAAABFESAAIgcDEwNzcxOTMwZGI1NGM0NDYwYTYwMzNhMjYzYjg3NzY3ZA'
)

task = {
    'task_id': 'e2e-test-001',
    'type': 'qwen_generate',
    'protocol_version': '1.0',
    'trace_id': 'trace-e2e-001',
    'payload': {
        'prompt': '运行测试',
        'workspace_path': 'd:\\generated'
    }
}

queue_name = 'task_queue:qwen'
r.delete('task_result:e2e-test-001')
r.lpush(queue_name, json.dumps(task, ensure_ascii=False))
print(f'Pushed task to {queue_name}: {task["task_id"]}')
print(f'Queue length: {r.llen(queue_name)}')