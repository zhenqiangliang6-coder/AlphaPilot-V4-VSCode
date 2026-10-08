"""Restore buggy code to test_v39_project"""
import os

PROJECT_DIR = r"D:\test_v39_project"

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

with open(os.path.join(PROJECT_DIR, "src/village_vote_system/models/candidate.py"), "w", encoding="utf-8") as f:
    f.write(CANDIDATE_BUGGY)
with open(os.path.join(PROJECT_DIR, "tests/test_vote.py"), "w", encoding="utf-8") as f:
    f.write(TEST_BUGGY)

print("Files restored to buggy state")

for fname in ["candidate.py", "test_vote.py"]:
    subdir = "src/village_vote_system/models" if "candidate" in fname else "tests"
    fp = os.path.join(PROJECT_DIR, subdir, fname)
    with open(fp, "r", encoding="utf-8") as f:
        code = f.read()
    try:
        compile(code, fname, "exec")
        print(f"  {fname}: OK")
    except SyntaxError as e:
        print(f"  {fname}: SYNTAX ERROR - {e}")