import json
import upstash_redis

r = upstash_redis.Redis(
    url='https://growing-cub-282898.upstash.io',
    token='gQAAAAAABFESAAIgcDEwNzcxOTMwZGI1NGM0NDYwYTYwMzNhMjYzYjg3NzY3ZA'
)

keys = [k for k in r.keys('*') if 'task_result' in k or 'd3ab0123' in k or 'e2100c7a' in k]
print(f'Found {len(keys)} keys')
for k in sorted(keys):
    val = r.get(k)
    if val:
        try:
            data = json.loads(val)
            tid = data.get('task_id','?')
            print(f'  {k} -> {tid}')
        except:
            print(f'  {k} -> (not json, len={len(val)})')

targets = ['d3ab0123-83dd-410d-b9fe-a24bd15ab071', 'e2100c7a-279a-455a-8e93-521d788f0511']
for tid in targets:
    result = r.get(f'task_result:{tid}')
    if result:
        data = json.loads(result)
        ctx = data.get('context', {})
        file_ops = ctx.get('final_file_ops', [])
        print(f'\n=== {tid} ===')
        print(f'  status: {data.get("status")}')
        print(f'  file_ops: {len(file_ops)}')
        for fo in file_ops:
            c = fo.get('content', '')
            print(f'    [{fo.get("op")}] {fo.get("path")} len={len(c)}')
            print(f'    content[:200]: {c[:200].replace(chr(10), chr(92)+"n")}')
    else:
        print(f'\n=== {tid} === NOT FOUND')