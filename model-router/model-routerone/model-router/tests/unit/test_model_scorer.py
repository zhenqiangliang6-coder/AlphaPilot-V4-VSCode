import pytest
from router.model_scorer import ModelScorer

def test_model_scorer_initialization():
    scorer = ModelScorer()
    assert scorer is not None

def test_score_models():
    scorer = ModelScorer()
    models = {
        "model_a": {"accuracy": 0.8, "latency": 200},
        "model_b": {"accuracy": 0.9, "latency": 150},
        "model_c": {"accuracy": 0.85, "latency": 180},
    }
    best_model = scorer.score_models(models)
    assert best_model == "model_b"

def test_score_models_with_tie():
    scorer = ModelScorer()
    models = {
        "model_a": {"accuracy": 0.9, "latency": 200},
        "model_b": {"accuracy": 0.9, "latency": 150},
    }
    best_model = scorer.score_models(models)
    assert best_model in ["model_a", "model_b"]

def test_score_models_empty():
    scorer = ModelScorer()
    models = {}
    best_model = scorer.score_models(models)
    assert best_model is None

def test_score_models_invalid_data():
    scorer = ModelScorer()
    models = {
        "model_a": {"accuracy": "high", "latency": 200},
    }
    with pytest.raises(ValueError):
        scorer.score_models(models)