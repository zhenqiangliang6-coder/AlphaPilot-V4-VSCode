# VS Code Extension Usage Example

## Overview
This document provides an example of how to use the ModelRouter project as a VS Code extension. The ModelRouter is designed to facilitate interactions with various AI models through a unified API.

## Installation
1. Clone the ModelRouter repository to your local machine.
2. Navigate to the project directory and set up a virtual environment:
   ```
   python -m venv venv
   venv\Scripts\activate
   ```
3. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

## Configuration
1. Create a `.env` file in the root directory based on the `.env.example` file, and set your API keys and other necessary environment variables.
2. Ensure that the FastAPI service is running:
   ```
   uvicorn model_router_api:app --reload
   ```

## Using the Extension
1. Open VS Code and navigate to the Command Palette (Ctrl + Shift + P).
2. Search for and select the command to interact with the ModelRouter.
3. Input your desired prompt or request in the provided input field.

## Example Request
To generate text using the ModelRouter, you can use the following example:

```json
{
  "model": "qwen-turbo",
  "input": "你好"
}
```

## Caching
The ModelRouter includes a caching mechanism to improve response times. Ensure that your caching strategy is configured correctly in `router/cache_manager.py`.

## Model Scoring
The ModelRouter automatically selects the best model based on performance metrics defined in `router/model_scorer.py`. Review the scoring logic to ensure it meets your requirements.

## Refactor Plan Generation
The extension supports generating refactor plans through the `router/plan_generator.py`. Customize the plan generation logic to fit your specific needs.

## Testing
Make sure to run the unit tests to verify the functionality of the caching and model scoring modules:
```
pytest tests/unit
```

## Documentation
Keep the documentation updated to assist other developers in understanding and using the ModelRouter effectively. Refer to the `docs` directory for detailed information on architecture, prompts, and deployment.

## Conclusion
This example serves as a guide for integrating the ModelRouter into a VS Code extension. Follow the steps outlined above to set up and utilize the project effectively.