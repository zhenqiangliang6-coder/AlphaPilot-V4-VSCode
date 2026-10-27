"""AlphaPilot E2E smoke test entry point.

Usage:
    python run_smoke_e2e.py           # Quick mode (mock memory)
    python run_smoke_e2e.py --full    # Real PostgreSQL memory mode
"""

from smoke_tests.runner import run

if __name__ == "__main__":
    run()