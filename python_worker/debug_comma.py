"""Debug: track where commas get deleted"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from test_autonomous import (_rule_based_syntax_fix, _commas_preserved,
                              test_compile_code, _fix_fixture)

PROJECT_DIR = r"D:\test_v39_project"

# 1. Inject buggy code WITH commas
CANDIDATE_BUGGY = (
    "class Candidate\n"
    "    def __init__(self, id: int, name: str):\n"
    "        self.id = id\n"
    "        self.name = name\n"
    "\n"
    "    def to_dict(self):\n"
    '        return {"id": self.id, "name": self.name}\n'
    "\n"
    "    @staticmethod\n"
    "    def load_all():\n"
    "        import json, os\n"
    '        data_path = os.path.join(os.path.dirname(__file__), "../../../data/candidates.json")\n'
    "        \n"
    '        with open(data_path, "r", encoding="utf-8") as f:\n'
    "            candidates = json.load(f)\n"
    "        \n"
    '        return [Candidate(c["id"], c["name"]) for c in candidates]\n'
)

TEST_BUGGY = (
    "import pytest, json, os, shutil, tempfile\n"
    "from src.village_vote_system.api.vote_router import cast_vote\n"
    "from src.village_vote_system.models.voter import Voter\n"
    "from src.village_vote_system.models.candidate import Candidate\n"
    "from src.village_vote_system.utils import validate_age, check_vote_eligibility, save_vote_data\n"
    "\n"
    "temp_dir = tempfile.mkdtemp()\n"
    'VOTERS_PATH = os.path.join(temp_dir, "voters.json")\n'
    'CANDIDATES_PATH = os.path.join(temp_dir, "candidates.json")\n'
    'VOTES_PATH = os.path.join(temp_dir, "votes.json")\n'
    "\n"
    "def cleanup():\n"
    "    shutil.rmtree(temp_dir)\n"
    "\n"
    'pytestmark = pytest.mark.usefixtures("cleanup"\n'
    "\n"
    "def setup_voter_data():\n"
    '    voters = [{"id": "123456", "name": "\u5f20\u4e09", "birth_date": "2000-01-01"}]\n'
    '    with open(VOTERS_PATH, "w") as f: json.dump(voters, f)\n'
    "\n"
    "def setup_candidate_data():\n"
    '    candidates = [{"id": 1, "name": "\u5019\u9009\u4ebaA"}, {"id": 2, "name": "\u5019\u9009\u4ebaB"}]\n'
    '    with open(CANDIDATES_PATH, "w") as f: json.dump(candidates, f)\n'
    "\n"
    "def test_cast_vote_success():\n"
    '    request = VoteRequest(voter_id="123456", candidate_id=1)\n'
    "    resp = cast_vote(request)\n"
    "    assert resp.success\n"
    "\n"
    "def test_cast_vote_already_voted():\n"
    '    request = VoteRequest(voter_id="654321", candidate_id=1)\n'
    "    resp = cast_vote(request)\n"
    "    assert not resp.success\n"
)

test_path = os.path.join(PROJECT_DIR, "tests", "test_vote.py")
candidate_path = os.path.join(PROJECT_DIR, "src", "village_vote_system", "models", "candidate.py")

with open(test_path, "w", encoding="utf-8") as f:
    f.write(TEST_BUGGY)
with open(candidate_path, "w", encoding="utf-8") as f:
    f.write(CANDIDATE_BUGGY)

print("=== Step 1: After inject ===")
with open(test_path, "r", encoding="utf-8") as f:
    code = f.read()
print(f"Test file commas: {code.count(',')}")
print(f"First line: {code.split(chr(10))[0]}")

# 2. Apply rule-based syntax fix for '(' was never closed
ok, err = test_compile_code(test_path, code)
print(f"\n=== Step 2: Compile check ===")
print(f"OK: {ok}, Error: {err}")

fixed = _rule_based_syntax_fix(code, err)
print(f"\n=== Step 3: After rule fix ===")
print(f"Fixed returned: {fixed is not None}")
if fixed:
    print(f"Commas: {fixed.count(',')} (was {code.count(',')})")
    ok2, err2 = test_compile_code(test_path, fixed)
    print(f"Re-compile: OK={ok2}, err={err2}")
    with open(test_path, "w", encoding="utf-8") as f:
        f.write(fixed)

# 4. Verify file on disk
print(f"\n=== Step 4: File on disk ===")
with open(test_path, "r", encoding="utf-8") as f:
    code2 = f.read()
print(f"Commas: {code2.count(',')}")
print(f"First 3 lines:")
for i, line in enumerate(code2.split('\n')[:3], 1):
    print(f"  {i}: {line[:100]}")