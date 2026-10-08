import json, os, sys
from pathlib import Path

WORKSPACE = Path(r"d:\generated")

backup_path = WORKSPACE / "test_vote.py"
with open(backup_path, "r", encoding="utf-8") as f:
    backup = json.load(f)
files_data = backup.get("files", {})

for fname, fdata in files_data.items():
    content = fdata.get("content", "")
    if content:
        filepath = WORKSPACE / fname
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Restored: {fname} ({len(content)} chars)")

main_content = """from flask import Flask
from api import api_bp

app = Flask(__name__)
app.register_blueprint(api_bp)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
"""
with open(WORKSPACE / "main.py", "w", encoding="utf-8") as f:
    f.write(main_content)
print("Created: main.py")

requirements = "flask>=2.0.0\npytest>=7.0.0\n"
with open(WORKSPACE / "requirements.txt", "w", encoding="utf-8") as f:
    f.write(requirements)
print("Created: requirements.txt")

print("Project files restored successfully.")