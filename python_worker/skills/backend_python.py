from .base import Skill


def register(registry):
    registry.register(
        Skill(
            id="backend.python",
            name="Python Backend Engineering",
            version="1.0.0",
            description="Guidance for AlphaPilot Python Workers, APIs, and backend services.",
            triggers=(
                "python",
                "worker",
                "fastapi",
                "flask",
                "backend",
                "api endpoint",
                "后端",
                "工作进程",
                "接口",
                "服务端",
            ),
            priority=60,
            capabilities=("workspace.read", "changes.propose", "tests.propose"),
            guidance=(
                "For backend work, follow the active Worker/API path and existing TaskModel "
                "contracts. Keep provider-specific code behind existing adapters, validate inputs, "
                "make failures observable, and add focused tests. Do not run project commands or "
                "apply workspace changes unless the host explicitly provides and authorizes them."
            ),
        )
    )
