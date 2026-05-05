# model_providers.py

import requests

class ModelProvider:
    def __init__(self, model_name):
        self.model_name = model_name

    def call_model(self, input_data):
        raise NotImplementedError("This method should be overridden by subclasses.")

class DeepSeekProvider(ModelProvider):
    def call_model(self, input_data):
        response = requests.post("https://api.deepseek.com/generate", json={"input": input_data})
        return response.json()

class QwenProvider(ModelProvider):
    def call_model(self, input_data):
        response = requests.post("https://api.qwen.com/generate", json={"input": input_data})
        return response.json()

class GeminiProvider(ModelProvider):
    def call_model(self, input_data):
        response = requests.post("https://api.gemini.com/generate", json={"input": input_data})
        return response.json()

class OpenAIProvider(ModelProvider):
    def call_model(self, input_data):
        response = requests.post("https://api.openai.com/v1/engines/davinci-codex/completions", 
                                 headers={"Authorization": f"Bearer {YOUR_API_KEY}"},
                                 json={"prompt": input_data, "max_tokens": 150})
        return response.json()

def get_model_provider(model_name):
    if model_name == "DeepSeek":
        return DeepSeekProvider(model_name)
    elif model_name == "Qwen":
        return QwenProvider(model_name)
    elif model_name == "Gemini":
        return GeminiProvider(model_name)
    elif model_name == "OpenAI":
        return OpenAIProvider(model_name)
    else:
        raise ValueError(f"Model {model_name} is not supported.")