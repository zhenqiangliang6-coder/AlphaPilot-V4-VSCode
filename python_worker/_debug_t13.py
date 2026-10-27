from task_state_contract import validate_result_contract, STEP_STATE_COMPLETED, STEP_STATE_SKIPPED, TASK_STATE_COMPLETED

result = {
    'version': '2.0', 'task_id': 't1', 'type': 'test',
    'status': 'done', 'task_state': TASK_STATE_COMPLETED,
    'result': 'text output',
    'steps': [
        {'id': 's1', 'type': 'a', 'status': STEP_STATE_COMPLETED},
        {'id': 's2', 'type': 'fix', 'status': STEP_STATE_SKIPPED},
        {'id': 's3', 'type': 't', 'status': STEP_STATE_COMPLETED},
    ],
    'events': [],
    'meta': {'started_at': 100, 'finished_at': 200, 'worker_id': 'w1', 'duration_ms': 100},
}

# trace extraction
steps_check = result.get("result", {}) if isinstance(result.get("result"), dict) else {}
steps_check = steps_check.get("steps", []) if isinstance(steps_check, dict) else (result.get("steps") or [])
print("extracted steps:", steps_check)

for i, s in enumerate(steps_check):
    status = s.get("status")
    reason = s.get("reason")
    print(f"step[{i}]: status={status!r} reason={reason!r}")
    if status == STEP_STATE_SKIPPED:
        print(f"  SKIPPED found, has reason: {bool(reason)}")
        if not reason:
            print(f"  -> SHOULD BE VIOLATION")

violations = validate_result_contract(result)
print("violations:", violations)
for v in violations:
    print(f"  {v.field}: {v.message}")