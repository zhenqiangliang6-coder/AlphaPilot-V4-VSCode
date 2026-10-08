from .base import Skill


def register(registry):
    registry.register(
        Skill(
            id="docker.infra",
            name="Docker Infrastructure",
            version="1.0.0",
            description="Guidance for Dockerfile, docker-compose, and container orchestration.",
            triggers=(
                "docker",
                "dockerfile",
                "docker-compose",
                "container",
                "image",
                "容器",
                "镜像",
                "docker build",
                "docker run",
                "compose",
                "orchestration",
            ),
            priority=130,
            capabilities=("workspace.read", "infra.propose", "dockerfile.propose"),
            guidance=(
                "For Docker work, follow multi-stage build best practices. Use alpine-based images for minimal size, "
                "minimize layer count, combine related RUN commands, expose only necessary ports. "
                "Implement health checks (HEALTHCHECK), handle graceful shutdown (SIGTERM), "
                "and use non-root users for security. In docker-compose, define service dependencies with depends_on, "
                "use environment variables for configuration, and add volume mounts for persistent data. "
                "For Python services, use virtual environments, copy requirements.txt before source for caching, "
                "and run with gunicorn/uvicorn for production. "
                "This skill only proposes Docker configurations: image building and container orchestration require host authorization."
            ),
        )
    )
