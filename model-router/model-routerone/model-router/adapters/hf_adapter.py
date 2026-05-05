# hf_adapter.py

import requests

class HFAdapter:
    def __init__(self, api_key: str, base_url: str = "https://api.huggingface.co"):
        self.api_key = api_key
        self.base_url = base_url

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def query_model(self, model_name: str, inputs: dict):
        url = f"{self.base_url}/models/{model_name}/generate"
        response = requests.post(url, headers=self._headers(), json=inputs)
        
        if response.status_code != 200:
            raise Exception(f"Error querying model: {response.text}")
        
        return response.json()

    def list_models(self):
        url = f"{self.base_url}/models"
        response = requests.get(url, headers=self._headers())
        
        if response.status_code != 200:
            raise Exception(f"Error listing models: {response.text}")
        
        return response.json()