import os
fp = r"D:\test_v39_project\tests\test_vote.py"
test_code = "import pytest, json, os, shutil, tempfile\n"
with open(fp, "w", encoding="utf-8") as f:
    f.write(test_code)
print("Wrote:", repr(test_code))
with open(fp, "r", encoding="utf-8") as f:
    content = f.read()
print("Read: ", repr(content))
print("Equal:", content == test_code)
print("Commas:", content.count(","))
# Show raw bytes
print("Bytes:", content[:40].encode("utf-8"))