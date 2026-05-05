# model-router/router/model_scorer.py

from typing import List, Dict, Any

class ModelScorer:
    def __init__(self, models: List[str]):
        self.models = models
        self.scores = {}

    def evaluate_model(self, model: str, input_data: Any) -> float:
        # Placeholder for model evaluation logic
        # This should return a score based on the model's performance
        return 0.0  # Replace with actual scoring logic

    def score_models(self, input_data: Any) -> Dict[str, float]:
        for model in self.models:
            score = self.evaluate_model(model, input_data)
            self.scores[model] = score
        return self.scores

    def select_best_model(self) -> str:
        if not self.scores:
            raise ValueError("No models have been scored yet.")
        best_model = max(self.scores, key=self.scores.get)
        return best_model

# Example usage:
# models = ['model_a', 'model_b', 'model_c']
# scorer = ModelScorer(models)
# scores = scorer.score_models(input_data)
# best_model = scorer.select_best_model()