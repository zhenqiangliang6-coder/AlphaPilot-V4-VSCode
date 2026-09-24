from python_worker.worker_config import redis
import sys
if len(sys.argv)<2:
    print('Usage: get_task_result.py <task_id>')
    sys.exit(2)
key=f"task_result:{sys.argv[1]}"
val=redis.get(key)
print(val)
