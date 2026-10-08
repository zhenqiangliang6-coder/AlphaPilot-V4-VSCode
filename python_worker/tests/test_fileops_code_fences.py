import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from file_ops import parse_fileops_v3


def test_fileops_removes_outer_markdown_fence_from_source_content():
    response = """# FILE: src/cli.py
```python
import numpy as np
print(np.array([1, 2]))
```
"""

    operations = parse_fileops_v3(response)

    assert len(operations) == 1
    assert operations[0]["content"] == "import numpy as np\nprint(np.array([1, 2]))"


def test_fileops_preserves_unwrapped_source_content():
    response = "# FILE: src/module.py\nprint('hello')"

    operations = parse_fileops_v3(response)

    assert operations[0]["content"] == "print('hello')"