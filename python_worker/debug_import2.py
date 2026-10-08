"""Quick test: call _fix_import with error logging"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv; load_dotenv()
from worker_config import DASHSCOPE_API_KEY
from test_autonomous import _fix_import,_project_map,_pm_text,llm_fixer

PROJECT_DIR = r"D:\test_v39_project"

# First call llm_fixer once to ensure _project_map and _pm_text are set
# Simulate with a dummy call that won't modify files
llm_fixer('no_tests', {}, '', {'project_dir': PROJECT_DIR})

print(f"\n_pm_text len: {len(_pm_text)}")
print(f"_pm_text preview: {_pm_text[:200]}")

print("\n--- Calling _fix_import ---")
error_info = {'name': 'VoteRequest', 'raw': "NameError: name 'VoteRequest' is not defined"}
test_output = "FAILED tests/test_vote.py::test_cast_vote_success - NameError: name 'VoteRequest' is not defined"
result = _fix_import(error_info, test_output, PROJECT_DIR)
print(f"\nResult: {result}")