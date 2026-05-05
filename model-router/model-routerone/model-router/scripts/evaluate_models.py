# evaluate_models.py

import json
import os
from router.model_scorer import ModelScorer
from router.cache_manager import CacheManager

def load_model_config(config_path):
    with open(config_path, 'r') as file:
        return json.load(file)

def evaluate_models(model_configs):
    scorer = ModelScorer()
    results = {}
    
    for model_name, model_info in model_configs.items():
        score = scorer.score_model(model_info)
        results[model_name] = score
    
    return results

def save_evaluation_results(results, output_path):
    with open(output_path, 'w') as file:
        json.dump(results, file, indent=4)

def main():
    config_path = os.getenv('MODEL_CONFIG_PATH', 'model_configs.json')
    output_path = os.getenv('EVALUATION_OUTPUT_PATH', 'evaluation_results.json')
    
    model_configs = load_model_config(config_path)
    evaluation_results = evaluate_models(model_configs)
    save_evaluation_results(evaluation_results, output_path)
    print(f"Evaluation results saved to {output_path}")

if __name__ == "__main__":
    main()