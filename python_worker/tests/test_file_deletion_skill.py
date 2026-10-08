import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from file_ops import contains_multi_file_protocol, parse_fileops_v3
from skills import route_skill


def test_delete_protocol_creates_candidate_operations_without_contents():
    operations = parse_fileops_v3(
        "# DELETE: src/obsolete.py\n# DELETE: docs/old-notes.md"
    )

    assert [operation["op"] for operation in operations] == ["delete", "delete"]
    assert [operation["path"] for operation in operations] == [
        "src/obsolete.py",
        "docs/old-notes.md",
    ]
    assert all(operation["content"] == "" for operation in operations)


def test_delete_marker_terminates_previous_file_content():
    operations = parse_fileops_v3(
        "# FILE: src/example.py\nprint('ok')\n# DELETE: src/obsolete.py"
    )

    assert operations[0]["content"] == "print('ok')"
    assert operations[1]["op"] == "delete"
    assert operations[1]["path"] == "src/obsolete.py"


def test_delete_protocol_is_registered_as_a_proposal_only_skill():
    skill = route_skill("请删除 src/obsolete.py")

    assert skill is not None
    assert skill.id == "workspace.file-deletion"
    assert "fileops.delete.propose" in skill.capabilities
    assert "永不" not in skill.guidance


def test_delete_protocol_counts_as_a_file_operation_protocol():
    assert contains_multi_file_protocol("# DELETE: src/obsolete.py")
