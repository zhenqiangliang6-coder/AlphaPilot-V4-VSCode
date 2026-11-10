import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from model_scorer import ModelScorer, ModelProfile


@pytest.fixture
def scorer():
    return ModelScorer(["Mock", "Qwen", "DeepSeek", "Gemini", "OpenAI"])


class TestInitialization:
    def test_requires_models_list(self, scorer):
        assert scorer.models == ["Mock", "Qwen", "DeepSeek", "Gemini", "OpenAI"]

    def test_uses_default_profiles(self, scorer):
        assert "Qwen" in scorer.profiles
        assert scorer.profiles["Mock"].available is True

    def test_accepts_custom_profiles(self):
        profiles = {"A": ModelProfile(success_rate=0.5), "B": ModelProfile(success_rate=0.8)}
        scorer = ModelScorer(["A", "B"], profiles=profiles)
        assert scorer.profiles["A"].success_rate == 0.5

    def test_accepts_custom_weights(self):
        weights = {"capability": 0.5, "success": 0.3, "latency": 0.1, "cost": 0.1}
        scorer = ModelScorer(["Mock"], weights=weights)
        assert scorer.weights["capability"] == 0.5


class TestBasicScoring:
    def test_returns_scores_for_all_models(self, scorer):
        scores = scorer.score_models({})
        assert set(scores.keys()) == set(scorer.models)

    def test_all_scores_in_zero_to_one_range(self, scorer):
        scores = scorer.score_models({})
        for model, score in scores.items():
            assert 0.0 <= score <= 1.0, f"{model} score {score} out of range"

    def test_selects_best_model(self, scorer):
        scorer.score_models({})
        best = scorer.select_best_model()
        assert best in scorer.models

    def test_raises_if_not_scored(self, scorer):
        with pytest.raises(ValueError, match="No models have been scored"):
            scorer.select_best_model()


class TestCapabilityScoring:
    def test_code_task_prefers_code_capable_models(self, scorer):
        scores = scorer.score_models({"metadata": {"task_type": "code"}})
        code_models = ["Qwen", "DeepSeek", "OpenAI"]
        general_only = ["Gemini"]

        for cm in code_models:
            for gm in general_only:
                assert scores[cm] > scores[gm], (
                    f"'{cm}' should beat '{gm}' on code task: "
                    f"{scores[cm]} vs {scores[gm]}"
                )

    def test_math_task_prefers_deepseek(self, scorer):
        scores = scorer.score_models({"metadata": {"task_type": "math"}})
        for model in ["Qwen", "Gemini", "OpenAI"]:
            assert scores["DeepSeek"] > scores[model], (
                f"DeepSeek should beat {model} on math task: "
                f"{scores['DeepSeek']} vs {scores[model]}"
            )

    def test_multimodal_task_prefers_gemini(self, scorer):
        scores = scorer.score_models({"metadata": {"task_type": "multimodal"}})
        for model in ["Qwen", "DeepSeek", "OpenAI"]:
            assert scores["Gemini"] > scores[model], (
                f"Gemini should beat {model} on multimodal task: "
                f"{scores['Gemini']} vs {scores[model]}"
            )

    def test_unknown_task_type_penalizes_all_equally_on_capability(self, scorer):
        scores = scorer.score_models({"metadata": {"task_type": "unknown"}})
        details = scorer.get_scoring_detail("Qwen")
        details_deepseek = scorer.get_scoring_detail("DeepSeek")
        details_gemini = scorer.get_scoring_detail("Gemini")
        assert details["capability"] == 0.3
        assert details_deepseek["capability"] == 0.3
        assert details_gemini["capability"] == 0.3


class TestAvailabilityScoring:
    def test_unavailable_model_scores_zero(self):
        profiles = {
            "A": ModelProfile(available=True, success_rate=0.9),
            "B": ModelProfile(available=False, success_rate=0.99),
        }
        scorer = ModelScorer(["A", "B"], profiles=profiles)
        scores = scorer.score_models({})
        assert scores["B"] == 0.0
        assert scores["A"] > 0.0

    def test_unavailable_not_selected(self):
        profiles = {
            "A": ModelProfile(available=True, success_rate=0.5),
            "B": ModelProfile(available=False, success_rate=0.99),
        }
        scorer = ModelScorer(["A", "B"], profiles=profiles)
        scorer.score_models({})
        assert scorer.select_best_model() == "A"


class TestDeterminism:
    def test_same_input_same_scores(self, scorer):
        scores1 = scorer.score_models({"metadata": {"task_type": "code"}})
        scores2 = scorer.score_models({"metadata": {"task_type": "code"}})
        assert scores1 == scores2

    def test_different_task_different_selection(self, scorer):
        real_scorer = ModelScorer(["Qwen", "DeepSeek", "Gemini", "OpenAI"])
        real_scorer.score_models({"metadata": {"task_type": "math"}})
        math_best = real_scorer.select_best_model()

        real_scorer.score_models({"metadata": {"task_type": "multimodal"}})
        multi_best = real_scorer.select_best_model()

        assert math_best != multi_best, (
            f"Different tasks should select different models: "
            f"math={math_best}, multimodal={multi_best}"
        )


class TestCustomWeights:
    def test_cost_only_weight_prefers_cheapest(self):
        weights = {"capability": 0.0, "success": 0.0, "latency": 0.0, "cost": 1.0}
        scorer = ModelScorer(["DeepSeek", "Gemini"], weights=weights)
        scorer.score_models({})
        assert scorer.select_best_model() == "DeepSeek"

    def test_latency_only_weight_prefers_fastest(self):
        weights = {"capability": 0.0, "success": 0.0, "latency": 1.0, "cost": 0.0}
        scorer = ModelScorer(["Qwen", "DeepSeek"], weights=weights)
        scorer.score_models({})
        assert scorer.select_best_model() == "Qwen"

    def test_success_only_weight_prefers_highest_rate(self):
        weights = {"capability": 0.0, "success": 1.0, "latency": 0.0, "cost": 0.0}
        scorer = ModelScorer(["Qwen", "OpenAI"], weights=weights)
        scorer.score_models({})
        assert scorer.select_best_model() == "OpenAI"


class TestScoringDetail:
    def test_detail_has_all_dimensions(self, scorer):
        scorer.score_models({})
        detail = scorer.get_scoring_detail("Qwen")
        assert "capability" in detail
        assert "success" in detail
        assert "latency" in detail
        assert "cost" in detail
        assert "total" in detail

    def test_detail_empty_for_unknown_model(self, scorer):
        scorer.score_models({})
        detail = scorer.get_scoring_detail("NonExistent")
        assert detail == {}


class TestAtomicScoreAndSelect:
    def test_returns_best_model_directly(self, scorer):
        best = scorer.score_and_select({})
        assert isinstance(best, str)
        assert best == "Mock"

    def test_scores_persisted_for_query(self, scorer):
        best = scorer.score_and_select({"metadata": {"task_type": "code"}})
        scores = scorer.scores
        assert len(scores) == len(scorer.models)
        assert best == max(scores, key=scores.get)

    def test_detail_persisted_after_atomic_call(self, scorer):
        scorer.score_and_select({})
        detail = scorer.get_scoring_detail("Qwen")
        assert "total" in detail

    def test_is_deterministic(self, scorer):
        best1 = scorer.score_and_select({})
        best2 = scorer.score_and_select({})
        assert best1 == best2