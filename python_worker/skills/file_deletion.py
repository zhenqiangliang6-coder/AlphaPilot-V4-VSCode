from .base import Skill


def register(registry):
    registry.register(
        Skill(
            id="workspace.file-deletion",
            name="Safe Workspace File Deletion",
            version="1.0.0",
            description="Propose workspace deletions through the host authorization and recycle-bin policy.",
            triggers=(
                "delete file",
                "delete files",
                "delete ",
                "remove file",
                "remove files",
                "remove ",
                "删除 ",
                "删除文件",
                "删除项目文件",
                "删除目录",
                "移除 ",
                "移除文件",
                "清理文件",
            ),
            priority=200,
            capabilities=("workspace.read", "fileops.delete.propose"),
            guidance=(
                "Deletion is proposal-only in the model. Emit one '# DELETE: relative/path' line per "
                "explicit target, with no content block. Never delete, rename, or overwrite files "
                "through code, shell commands, or other FileOps. Do not guess paths or expand a "
                "directory into individual files. If a target is ambiguous, ask for its exact path. "
                "The host validates containment and sensitive paths, moves a single file to the "
                "recycle bin automatically, and requires confirmation for batches and directories. "
                "Never propose deletion of .git, .env*, node_modules, venv, .venv, __pycache__, "
                "dist, or build."
            ),
        )
    )
