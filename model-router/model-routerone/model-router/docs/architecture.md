# Architecture Overview of ModelRouter Project

## Project Structure

The ModelRouter project is organized into several key directories and files, each serving a specific purpose:

```
model-router/
├── model_router_api.py        # Entry point for FastAPI service
├── router/
│   ├── __init__.py            # Initializes the router module
│   ├── model_router.py         # Main router containing core logic
│   ├── cache_manager.py        # Manages caching to improve speed
│   ├── model_scorer.py         # Automatically selects the strongest model
│   ├── plan_generator.py        # Generates refactor plans
│   ├── prompt_builder.py        # Constructs prompts for requests
│   ├── diff_utils.py           # Generates diffs for model outputs
│   ├── dependency_analyzer.py   # Analyzes dependencies between models
│   ├── model_providers.py      # Calls models like DeepSeek, Qwen, Gemini, and OpenAI
│   └── schemas.py              # Defines data schemas for consistency
├── adapters/
│   ├── __init__.py            # Initializes the adapters module
│   ├── redis_adapter.py        # Interacts with Redis database
│   ├── sqlite_adapter.py       # Interacts with SQLite database
│   └── hf_adapter.py           # Interacts with Hugging Face API
├── scripts/
│   ├── seed_cache.py           # Fills the cache with initial data
│   └── evaluate_models.py      # Evaluates model performance
├── tests/
│   ├── unit/
│   │   ├── test_cache_manager.py # Unit tests for cache manager
│   │   ├── test_model_scorer.py  # Unit tests for model scorer
│   │   └── test_plan_generator.py # Unit tests for plan generator
│   └── integration/
│       └── test_api.py          # Integration tests for API functionality
├── docs/
│   ├── architecture.md          # Documentation describing project architecture
│   ├── prompts.md               # Documentation for prompt usage
│   ├── refactor_plan_templates.md # Templates for refactor plans
│   └── deployment.md            # Deployment instructions
├── examples/
│   ├── curl_examples.md         # Examples of using curl to test the API
│   └── vscode_extension.md      # Examples for using the VS Code extension
├── .env.example                  # Example environment variable configuration
├── .gitignore                    # Files and directories to ignore in Git
├── requirements.txt              # List of project dependencies
├── pyproject.toml               # Project configuration file
├── Dockerfile                    # Docker image build file
├── docker-compose.yml            # Docker Compose configuration
├── .github/
│   └── workflows/
│       └── ci.yml               # CI configuration for GitHub Actions
└── README.md                    # Overview and usage instructions for the project
```

## Key Components

1. **FastAPI Service**: The `model_router_api.py` file serves as the entry point for the FastAPI service, handling incoming requests and routing them appropriately.

2. **Router Logic**: The `router/model_router.py` file contains the core routing logic, directing requests to the appropriate handlers based on the input.

3. **Caching**: The `router/cache_manager.py` file implements caching mechanisms to enhance performance, allowing for faster response times by storing frequently accessed data.

4. **Model Scoring**: The `router/model_scorer.py` file is responsible for evaluating models and automatically selecting the best-performing one based on predefined criteria.

5. **Refactor Plan Generation**: The `router/plan_generator.py` file generates refactor plans, providing a structured approach to modifying and improving the codebase.

6. **Prompt Construction**: The `router/prompt_builder.py` file constructs prompts for model requests, ensuring that the input is formatted correctly for optimal results.

7. **Dependency Analysis**: The `router/dependency_analyzer.py` file analyzes the dependencies between different models, helping to identify potential issues and optimize interactions.

8. **Model Providers**: The `router/model_providers.py` file manages interactions with various models, including DeepSeek, Qwen, Gemini, and OpenAI, facilitating seamless integration.

## Tips and Considerations

1. **Virtual Environment**: Ensure all dependencies are installed within a virtual environment. Activate it using the command: `venv\Scripts\activate`.

2. **Caching Strategy**: When implementing caching, consider selecting an appropriate caching strategy to maximize performance benefits.

3. **Model Scoring Logic**: Ensure the scoring logic in the model scorer is accurate to facilitate the automatic selection of the best model.

4. **Flexibility in Plan Generation**: The refactor plan generator should be flexible enough to accommodate various refactoring needs.

5. **Testing Coverage**: Write comprehensive tests to cover all critical functionalities, especially for the caching and model scoring modules.

6. **Documentation Maintenance**: Keep documentation up to date to help other developers quickly understand and contribute to the project.