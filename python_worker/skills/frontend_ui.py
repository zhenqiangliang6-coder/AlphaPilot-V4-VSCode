from .base import Skill


def register(registry):
    registry.register(
        Skill(
            id="frontend.ui",
            name="Frontend UI Engineering",
            version="1.0.0",
            description="Guidance for VS Code Extension, TypeScript, React, and Webview work.",
            triggers=(
                "frontend",
                "front-end",
                "webview",
                "react",
                "typescript ui",
                "vscode extension",
                "界面",
                "前端",
                "网页",
                "组件",
            ),
            priority=70,
            capabilities=("workspace.read", "changes.propose"),
            guidance=(
                "For UI work, first inspect the existing VS Code Extension/Webview boundaries, "
                "component patterns, message protocol, and build scripts. Propose focused changes; "
                "preserve accessibility, loading/error states, and existing behavior. Do not claim "
                "to have changed files or run the UI unless the host confirms it."
            ),
        )
    )
