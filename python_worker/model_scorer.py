import threading
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class ModelProfile:
    capabilities: List[str] = field(default_factory=lambda: ["general"])
    cost_per_1k_tokens: float = 0.0
    avg_latency_ms: float = 500.0
    success_rate: float = 0.9
    available: bool = True


DEFAULT_PROFILES: Dict[str, ModelProfile] = {
    "Mock": ModelProfile(
        capabilities=["mock"],
        cost_per_1k_tokens=0.0,
        avg_latency_ms=0.0,
        success_rate=1.0,
        available=True,
    ),
    "Qwen": ModelProfile(
        capabilities=["general", "code", "chat"],
        cost_per_1k_tokens=0.002,
        avg_latency_ms=800.0,
        success_rate=0.95,
        available=True,
    ),
    "DeepSeek": ModelProfile(
        capabilities=["general", "code", "math"],
        cost_per_1k_tokens=0.0014,
        avg_latency_ms=1200.0,
        success_rate=0.93,
        available=True,
    ),
    "Gemini": ModelProfile(
        capabilities=["general", "multimodal", "chat"],
        cost_per_1k_tokens=0.0025,
        avg_latency_ms=900.0,
        success_rate=0.94,
        available=True,
    ),
    "OpenAI": ModelProfile(
        capabilities=["general", "code", "chat"],
        cost_per_1k_tokens=0.002,
        avg_latency_ms=700.0,
        success_rate=0.96,
        available=True,
    ),
}

DEFAULT_WEIGHTS: Dict[str, float] = {
    "capability": 0.25,
    "success": 0.25,
    "latency": 0.25,
    "cost": 0.25,
}


class ModelScorer:
    def __init__(
        self,
        models: List[str],
        profiles: Optional[Dict[str, ModelProfile]] = None,
        weights: Optional[Dict[str, float]] = None,
    ):
        self.models = models
        self.profiles = profiles or DEFAULT_PROFILES
        self.weights = weights or DEFAULT_WEIGHTS
        self.scores: Dict[str, float] = {}
        self._detail: Dict[str, Dict[str, float]] = {}
        self._lock = threading.Lock()

    def score_and_select(self, input_data: Dict[str, Any]) -> str:
        with self._lock:
            self.scores = {}
            self._detail = {}
            for model in self.models:
                score, detail = self._score_model(model, input_data)
                self.scores[model] = score
                self._detail[model] = detail
            return max(self.scores, key=self.scores.get)

    def score_models(self, input_data: Dict[str, Any]) -> Dict[str, float]:
        with self._lock:
            self.scores = {}
            self._detail = {}
            for model in self.models:
                score, detail = self._score_model(model, input_data)
                self.scores[model] = score
                self._detail[model] = detail
            return dict(self.scores)

    def select_best_model(self) -> str:
        with self._lock:
            if not self.scores:
                raise ValueError("No models have been scored yet.")
            best_model = max(self.scores, key=self.scores.get)
            return best_model

    def get_scoring_detail(self, model: str) -> Dict[str, float]:
        return self._detail.get(model, {})

    def _score_model(
        self, model: str, input_data: Dict[str, Any]
    ) -> tuple[float, Dict[str, float]]:
        profile = self.profiles.get(model, ModelProfile())

        if not profile.available:
            return 0.0, {"available": 0.0}

        task_type = input_data.get("metadata", {}).get("task_type", "general")

        cap_score = 1.0 if task_type in profile.capabilities else 0.3
        suc_score = profile.success_rate

        all_latencies = [p.avg_latency_ms for p in self.profiles.values() if p.available]
        max_latency = max(all_latencies) if all_latencies else 1
        lat_score = (
            1.0 - (profile.avg_latency_ms / max_latency)
            if max_latency > 0
            else 1.0
        )

        all_costs = [p.cost_per_1k_tokens for p in self.profiles.values() if p.available]
        max_cost = max(all_costs) if all_costs else 1
        cost_score = (
            1.0 - (profile.cost_per_1k_tokens / max_cost)
            if max_cost > 0
            else 1.0
        )

        score = (
            self.weights["capability"] * cap_score
            + self.weights["success"] * suc_score
            + self.weights["latency"] * lat_score
            + self.weights["cost"] * cost_score
        )
        score = round(score, 4)

        detail = {
            "capability": cap_score,
            "success": suc_score,
            "latency": lat_score,
            "cost": cost_score,
            "total": score,
        }

        return score, detail