"""Quick debug: test _fix_import LLM response"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv; load_dotenv()
from worker_config import DASHSCOPE_API_KEY
from test_autonomous import (
    qwen, extract_code, _pm_text, _project_map,
    build_project_map, format_project_map, validate_imports,
    _commas_preserved
)

PROJECT_DIR = r"D:\test_v39_project"

# Build project map
pm = build_project_map(PROJECT_DIR)
pm_text = format_project_map(pm)

# Read test file (should have @pytest.fixture already from previous run)
test_file = os.path.join(PROJECT_DIR, 'tests', 'test_vote.py')
if not os.path.exists(test_file):
    # If file was cleaned up, create a minimal version
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write("""import pytest, json, os, shutil, tempfile
from src.village_vote_system.api.vote_router import cast_vote
from src.village_vote_system.models.voter import Voter
from src.village_vote_system.models.candidate import Candidate
from src.village_vote_system.utils import validate_age, check_vote_eligibility, save_vote_data

temp_dir = tempfile.mkdtemp()
VOTERS_PATH = os.path.join(temp_dir, "voters.json")
CANDIDATES_PATH = os.path.join(temp_dir, "candidates.json")
VOTES_PATH = os.path.join(temp_dir, "votes.json")

@pytest.fixture
def cleanup():
    shutil.rmtree(temp_dir)

pytestmark = pytest.mark.usefixtures("cleanup")

def setup_voter_data():
    voters = [{"id": "123456", "name": "Zhang San", "birth_date": "2000-01-01"}]
    with open(VOTERS_PATH, "w") as f: json.dump(voters, f)

def setup_candidate_data():
    candidates = [{"id": 1, "name": "Candidate A"}, {"id": 2, "name": "Candidate B"}]
    with open(CANDIDATES_PATH, "w") as f: json.dump(candidates, f)

def test_cast_vote_success():
    request = VoteRequest(voter_id="123456", candidate_id=1)
    resp = cast_vote(request)
    assert resp.success

def test_cast_vote_already_voted():
    request = VoteRequest(voter_id="654321", candidate_id=1)
    resp = cast_vote(request)
    assert not resp.success
""")

with open(test_file, 'r', encoding='utf-8') as f:
    code = f.read()

rel = 'tests/test_vote.py'
import_name = 'VoteRequest'

prompt = f"""{pm_text}

你是 Python import 修复专家。

【错误】: cannot import '{import_name}'
【文件】: {rel}

【错误输出】:
NameError: name 'VoteRequest' is not defined

【代码】:
```python
{code}
```

【项目地图已标注每个符号的正确导入路径，请严格按地图修复 import】
只输出 ```python 代码块。"""

print(f"Prompt length: {len(prompt)}")
print(f"Project map section: ...")
print(f"--- Sending to LLM ---")
resp = qwen(prompt)
print(f"Response length: {len(resp)}")
print(f"Response preview: {repr(resp[:500])}")
print(f"--- Extracting ---")
fixed = extract_code(resp)
print(f"Extracted length: {len(fixed) if fixed else 0}")
if fixed:
    print(f"Has VoteRequest import: {'VoteRequest' in fixed}")
    print(f"Commas preserved: {_commas_preserved(code, fixed)}")
    print(f"First 200 chars: {fixed[:200]}")