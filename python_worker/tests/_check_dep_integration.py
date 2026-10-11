"""Quick integration check: verify unified_dependencies in scan output."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from context_builder import inspect_python_project

scan = inspect_python_project(".")
print("dependency_manifests:", scan.get("dependency_manifests"))
print("inferred_dependencies:", scan.get("inferred_dependencies"))
print("unified_dependencies:")
for d in scan.get("unified_dependencies", []):
    print(f"  {d['name']:20s}  sources={d['sources']}  signals={d['signal_count']}")
print("dependency_summary:", scan.get("dependency_summary"))