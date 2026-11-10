"""v3.6 file_ops parser tests: multi-language FILE markers + fence stripping."""
import sys
sys.path.insert(0, "..")

from file_ops import (
    parse_fileops_v3, FILE_PATTERN, HTML_FILE_PATTERN,
    _is_block_marker, _strip_markdown_fences, extract_block
)


def test_basic_python():
    r = parse_fileops_v3("# FILE: app.py\nprint('hello')\n")
    assert len(r) == 1
    assert r[0]["path"] == "app.py"
    assert "print" in r[0]["content"]


def test_ts_style():
    r = parse_fileops_v3("// FILE: App.tsx\nconst x = 1;\n")
    assert len(r) == 1, f"Expected 1, got {len(r)}: {[op['path'] for op in r]}"
    assert r[0]["path"] == "App.tsx"
    assert "const x" in r[0]["content"]


def test_css_style():
    r = parse_fileops_v3("/* FILE: style.css */\nbody { margin: 0; }\n")
    assert len(r) == 1
    assert r[0]["path"] == "style.css"
    assert "body" in r[0]["content"]


def test_mixed_multi_lang():
    mixed = """# FILE: main.py
from fastapi import FastAPI
app = FastAPI()

// FILE: App.tsx
import React from 'react';
export default function App() { return null; }

# FILE: test_api.py
def test_foo():
    pass
"""
    r = parse_fileops_v3(mixed)
    paths = [op["path"] for op in r]
    assert paths == ["main.py", "App.tsx", "test_api.py"], f"Got: {paths}"


def test_fence_stripping():
    fenced = """# FILE: app.py
```python
from fastapi import FastAPI
app = FastAPI()
```

// FILE: index.ts
```typescript
const x = 1;
```"""
    r = parse_fileops_v3(fenced)
    for op in r:
        assert "```" not in op["content"], f"{op['path']} has fence: {op['content'][:100]}"


def test_nested_fences():
    nested = """```
# FILE: app.py
```python
from fastapi import FastAPI
```

// FILE: App.tsx
```typescript
const x = 1;
```
```"""
    r = parse_fileops_v3(nested)
    for op in r:
        assert "```" not in op["content"], f"{op['path']} still has fences"


def test__is_block_marker():
    assert _is_block_marker("# FILE: test.py")
    assert _is_block_marker("// FILE: test.ts")
    assert _is_block_marker("/* FILE: test.css */")
    assert _is_block_marker("# TEST: test.py")
    assert _is_block_marker("// TEST: test.ts")
    assert _is_block_marker("  // FILE: test.tsx  ")  # with whitespace
    assert not _is_block_marker("import os")


def test_block_marker_break():
    """Ensure // FILE: stops a preceding # FILE: block"""
    mixed = "# FILE: backend.py\nimport os\n\n// FILE: frontend.ts\nconst x = 1;\n"
    r = parse_fileops_v3(mixed)
    paths = [op["path"] for op in r]
    assert "backend.py" in paths
    assert "frontend.ts" in paths
    for op in r:
        if op["path"] == "backend.py":
            assert "const x" not in op["content"], f"backend.py leaked TS code!"
            assert "import os" in op["content"]


if __name__ == "__main__":
    test_basic_python(); print("  PASS: basic_python")
    test_ts_style();      print("  PASS: ts_style")
    test_css_style();     print("  PASS: css_style")
    test_mixed_multi_lang(); print("  PASS: mixed_multi_lang")
    test_fence_stripping();  print("  PASS: fence_stripping")
    test_nested_fences();    print("  PASS: nested_fences")
    test__is_block_marker(); print("  PASS: _is_block_marker")
    test_block_marker_break(); print("  PASS: block_marker_break")
    print("\nALL v3.6 file_ops TESTS PASSED")