from pydantic import BaseModel
from typing import List, Optional

class ModelSchema(BaseModel):
    name: str
    version: str
    accuracy: float
    latency: float
    provider: str

class CacheSchema(BaseModel):
    key: str
    value: str
    expiration: Optional[int] = None

class RefactorPlanSchema(BaseModel):
    plan_id: str
    description: str
    steps: List[str]

class PromptSchema(BaseModel):
    model_name: str
    input_text: str
    output_format: str

class DependencySchema(BaseModel):
    model_name: str
    dependencies: List[str]