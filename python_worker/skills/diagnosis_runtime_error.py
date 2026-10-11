from .base import Skill


def register(registry):
    registry.register(
        Skill(
            id="diagnosis.runtime-error",
            name="Runtime Error Diagnosis & Targeted Fix",
            version="1.0.0",
            description="Diagnose runtime errors from logs; apply minimum-viable fix to config/env/code without modifying unrelated logic.",
            triggers=(
                "端口被占用", "Address already in use", "ConnectionRefused",
                "ConnectionReset",
                "Errno 10048", "Errno 10061", "Errno 10054",
                "Errno 13", "Permission denied",
                "运行时错误", "运行报错",
                "配置文件错误", "环境变量",
            ),
            priority=90,
            capabilities=("workspace.read", "workspace.write", "diagnosis.log"),
            output_profile={
                "output_mode": "code",
                "workspace_dependency": "read_write",
                "requires_workspace_scan": True,
                "requires_test": False,
            },
            guidance=(
                "You are a runtime error diagnosis expert. "
                "Analyze the error log provided by the user. Focus ONLY on the specific code line or "
                "configuration file that the error message points to. "
                "Perform a MINIMUM-VIABLE fix: only modify the specific config/port/permission/env-var "
                "that caused the error. "
                "ABSOLUTELY DO NOT modify any unrelated business logic, algorithms, or data structures. "
                "For port conflicts (Errno 10048/10061/Address already in use): check existing process "
                "occupancy and suggest a different port; do NOT rewrite the application's HTTP handler code. "
                "For permission errors (Errno 13/Permission denied): check file/directory permissions; "
                "do NOT rewrite file I/O logic. "
                "For missing environment variables or config errors: locate the relevant .env/config file "
                "and add/fix the variable; do NOT restructure the application. "
                "After the fix, report ONLY what was changed and why. Do not add any extra features, "
                "refactoring, or optimizations."
            ),
        )
    )