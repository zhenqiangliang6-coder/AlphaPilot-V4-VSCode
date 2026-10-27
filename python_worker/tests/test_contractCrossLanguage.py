import json
import os
import sys
from typing import Any, Dict, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from task_state_contract import (
    TASK_STATE_TO_LEGACY_STATUS,
    TASK_STATES_ALL,
    LEGACY_STATUS_TO_TASK_STATE,
)

VALID_STATUS_VALUES = {"done", "error", "pending", "awaiting_authorization"}


def resolve_contract(input_dict: Any) -> Dict[str, Any]:
    """
    Cross-language state resolver using Python's contract constants.
    Logic mirrors Node.js resolveStatus() and TypeScript resolveTaskStatus()
    to ensure identical judgment for the same input.
    """
    if input_dict is None or not isinstance(input_dict, dict):
        return {"status": None, "valid": False}

    raw_task_state = input_dict.get("task_state")
    raw_status = input_dict.get("status")

    has_task_state = isinstance(raw_task_state, str) and raw_task_state.strip() != ""
    has_status = isinstance(raw_status, str) and raw_status.strip() != ""
    task_state = raw_task_state.strip() if has_task_state else None
    status_val = raw_status.strip() if has_status else None

    if not has_task_state and not has_status:
        return {"status": None, "valid": False}

    if not has_task_state:
        if status_val and status_val in VALID_STATUS_VALUES:
            return {"status": status_val, "valid": True}
        return {"status": None, "valid": False}

    if task_state not in TASK_STATES_ALL:
        return {"status": None, "valid": False}

    expected_status = TASK_STATE_TO_LEGACY_STATUS.get(task_state)

    if not has_status:
        return {"status": expected_status, "valid": True}

    if status_val == expected_status:
        return {"status": status_val, "valid": True}

    if task_state == "COMPLETED" and status_val == "completed":
        return {"status": "done", "valid": True}

    return {"status": None, "valid": False}


def main():
    vectors_path = os.path.join(
        os.path.dirname(__file__), '..', '..', 'contract-test-vectors.json'
    )
    with open(vectors_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    vectors = data['vectors']

    passes = []
    divergence_failures = []
    failures = []

    for v in vectors:
        resolved = resolve_contract(v.get('input'))
        expected = v['expected']

        passed = True
        mismatches = []

        if resolved['valid'] != expected['valid']:
            passed = False
            mismatches.append(
                f"valid: got {resolved['valid']}, expected {expected['valid']}"
            )

        if resolved['status'] != expected['status']:
            passed = False
            mismatches.append(
                f"status: got {resolved['status']!r}, expected {expected['status']!r}"
            )

        is_divergence = v.get('category') == 'KNOWN_DIVERGENCE'

        if passed:
            passes.append(v['id'])
        elif is_divergence:
            divergence_failures.append({
                'id': v['id'],
                'mismatches': mismatches,
                'description': v.get('description', ''),
            })
        else:
            failures.append({
                'id': v['id'],
                'mismatches': mismatches,
                'description': v.get('description', ''),
            })

    if failures:
        print(f"\n❌ {len(failures)} UNEXPECTED failures:")
        for f in failures:
            print(f"   {f['id']}: {'; '.join(f['mismatches'])}")
            print(f"      desc: {f['description']}")

    if divergence_failures:
        print(f"\n⚠️ {len(divergence_failures)} KNOWN DIVERGENCE failures:")
        for f in divergence_failures:
            print(f"   {f['id']}: {'; '.join(f['mismatches'])}")
            print(f"      desc: {f['description']}")

    total = len(vectors)
    print(f"\n✅ {len(passes)}/{total} passed")
    print(f"⚠️ {len(divergence_failures)} known divergence failures")
    print(f"❌ {len(failures)} unexpected failures")

    assert len(failures) == 0, f"{len(failures)} unexpected failures"
    print("ALL PASSED" if len(failures) == 0 else "FAILURES DETECTED")


if __name__ == '__main__':
    main()