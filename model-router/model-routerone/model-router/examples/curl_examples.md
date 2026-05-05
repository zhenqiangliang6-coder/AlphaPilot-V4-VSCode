# curl_examples.md

# Curl Examples for ModelRouter API

This document provides examples of how to use `curl` to interact with the ModelRouter API. These examples demonstrate how to send requests to the API endpoints and receive responses.

## Example 1: Text Generation

To generate text using the ModelRouter API, you can use the following `curl` command:

```bash
curl -X POST https://your-api-url/api/v1/generate-text \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen-turbo","input":"你好"}'
```

### Explanation:
- Replace `https://your-api-url` with the actual URL of your ModelRouter API.
- Replace `YOUR_API_KEY` with your actual API key.
- The `input` field contains the text prompt you want to send to the model.

## Example 2: Model Scoring

To score models and select the best one, you can use the following command:

```bash
curl -X POST https://your-api-url/api/v1/score-models \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"models":["model1","model2","model3"],"input":"测试文本"}'
```

### Explanation:
- The `models` array should contain the names of the models you want to score.
- The `input` field is the text you want to evaluate against the models.

## Example 3: Generate Refactor Plan

To generate a refactor plan, use the following command:

```bash
curl -X POST https://your-api-url/api/v1/generate-plan \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"project_structure":"your_project_structure_here"}'
```

### Explanation:
- The `project_structure` field should describe the structure of your project for which you want to generate a refactor plan.

## Notes
- Ensure that you have the necessary permissions and that your API key is valid.
- Adjust the endpoints and payloads according to your specific API implementation.
- Test each command in your terminal to verify functionality.