import json, upstash_redis

r = upstash_redis.Redis(
    url='https://growing-cub-282898.upstash.io',
    token='gQAAAAAABFESAAIgcDEwNzcxOTMwZGI1NGM0NDYwYTYwMzNhMjYzYjg3NzY3ZA'
)

result = r.get('task_result:e2e-test-001')
if result:
    data = json.loads(result)
    print('=' * 60)
    print('TASK RESULT FOUND!')
    print('=' * 60)
    status = data.get('status', 'unknown')
    print(f'Status: {status}')
    print(f'Task ID: {data.get("task_id")}')
    
    if status == 'success':
        output = data.get('result', '')
        print(f'Output length: {len(output)} chars')
        print(f'Output preview (first 500):')
        print(output[:500])
        print(f'\nOutput preview (last 300):')
        print(output[-300:])
        
        meta = data.get('context', {}).get('meta', {})
        scan = meta.get('workspace_scan', {})
        if scan:
            print(f'\n[WORKSPACE SCAN ACTIVE ✅]')
            print(f'  Files scanned: {scan.get("python_file_count", 0)}')
            print(f'  Root: {scan.get("root")}')
        else:
            print('\n[NO WORKSPACE SCAN ❌]')
            
        # Check steps
        steps = data.get('steps', [])
        print(f'\nSteps completed: {len(steps)}')
        for s in steps:
            st = s.get('status', '?')
            stype = s.get('type', '?')
            print(f'  [{st}] {stype}')
        
    elif status == 'error':
        print(f'Error: {data.get("error", "unknown")}')
else:
    print('No result yet - LLM still generating...')