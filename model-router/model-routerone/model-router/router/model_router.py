from fastapi import FastAPI, HTTPException
from router.cache_manager import CacheManager
from router.model_scorer import ModelScorer
from router.plan_generator import PlanGenerator
from router.prompt_builder import PromptBuilder
from router.model_providers import ModelProviders

app = FastAPI()

cache_manager = CacheManager()
model_scorer = ModelScorer()
plan_generator = PlanGenerator()
prompt_builder = PromptBuilder()
model_providers = ModelProviders()

@app.post("/generate")
async def generate(input_data: dict):
    try:
        prompt = prompt_builder.build_prompt(input_data)
        cached_response = cache_manager.get_from_cache(prompt)
        
        if cached_response:
            return cached_response
        
        model_scores = model_scorer.score_models(input_data)
        best_model = model_scores.get("best_model")
        
        response = await model_providers.call_model(best_model, prompt)
        cache_manager.save_to_cache(prompt, response)
        
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/refactor")
async def refactor(input_data: dict):
    try:
        plan = plan_generator.generate_plan(input_data)
        return plan
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))