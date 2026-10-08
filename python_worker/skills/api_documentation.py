from .base import Skill


def register(registry):
    registry.register(
        Skill(
            id="api.documentation",
            name="API Documentation",
            version="1.0.0",
            description="Guidance for API documentation (Node.js/FastAPI), request/response schemas, and interface specifications.",
            triggers=(
                "api doc",
                "api documentation",
                "interface doc",
                "endpoint doc",
                "swagger",
                "openapi",
                "接口文档",
                "API文档",
                "接口说明",
                "接口定义",
                "endpoint",
                "rest api",
                "生成文档",
                "文档说明",
                "写文档",
                "api 说明",
            ),
            priority=110,
            capabilities=("workspace.read", "docs.propose", "schema.propose"),
            guidance=(
                "For API documentation, clearly define request/response structures, error codes, authentication methods, "
                "and example requests. For Node.js APIs (Express/Fastify), document routes, middleware, request body schemas, "
                "query parameters, and response formats. For FastAPI, leverage Pydantic models for automatic schema generation, "
                "use /docs and /openapi.json endpoints, and add comprehensive docstrings to route handlers. "
                "Include authentication details (API keys, JWT, OAuth), rate limiting info, and error response formats. "
                "Provide example curl commands or Postman collections for testing. "
                "Note: This skill is for documenting your own APIs (Node.js/FastAPI), not for calling external AI services. "
                "External AI model calls (e.g., DASHSCOPE_API for Qwen) are implemented in the worker's adapters layer. "
                "This skill only proposes documentation changes: actual API changes require host authorization."
            ),
        )
    )
