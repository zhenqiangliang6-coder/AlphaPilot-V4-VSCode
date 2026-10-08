from .base import Skill


def register(registry):
    registry.register(
        Skill(
            id="dependency.manager",
            name="Dependency Management",
            version="1.0.0",
            description="Guidance for reviewing and proposing dependency and lockfile changes.",
            triggers=(
                "dependency",
                "dependencies",
                "package.json",
                "package-lock",
                "requirements.txt",
                "pyproject.toml",
                "install package",
                "upgrade package",
                "依赖",
                "升级包",
                "安装包",
            ),
            priority=100,
            capabilities=("manifest.read", "changes.propose"),
            guidance=(
                "For dependency work, identify the owning manifest and lockfile, distinguish direct "
                "from transitive changes, and check runtime/test compatibility. This skill only "
                "reviews and proposes changes: package installation, network access, and lockfile "
                "mutation are unavailable until an authorized host capability is implemented."
            ),
        )
    )
