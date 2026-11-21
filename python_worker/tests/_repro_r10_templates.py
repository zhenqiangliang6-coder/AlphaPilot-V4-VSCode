import os, sys, subprocess, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gate_refactor import TEMPLATES  # noqa: E402

def main():
    root = Path(tempfile.mkdtemp(prefix="repro-r10-"))
    for rel, src in TEMPLATES.items():
        t = root / rel
        t.parent.mkdir(parents=True, exist_ok=True)
        t.write_text(src, encoding="utf-8")
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(root)}
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--disable-warnings"],
        cwd=str(root), capture_output=True, text=True, timeout=120, env=env)
    print("ROOT:", root)
    print("RC:", proc.returncode)
    print("STDOUT:", proc.stdout[-4000:])
    print("STDERR:", proc.stderr[-4000:])

if __name__ == "__main__":
    main()