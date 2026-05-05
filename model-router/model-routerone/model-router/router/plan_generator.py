# plan_generator.py

from typing import List, Dict, Any

class RefactorPlanGenerator:
    def __init__(self):
        pass

    def generate_plan(self, model_outputs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        生成重构计划，根据模型输出的结果。
        
        :param model_outputs: 模型输出的列表，每个输出包含模型名称和结果
        :return: 重构计划的字典
        """
        plan = {
            "steps": [],
            "recommendations": []
        }

        for output in model_outputs:
            model_name = output.get("model_name")
            result = output.get("result")

            # 根据模型输出生成重构步骤
            if result:
                plan["steps"].append(self.create_step(model_name, result))
                plan["recommendations"].append(self.create_recommendation(model_name, result))

        return plan

    def create_step(self, model_name: str, result: Any) -> Dict[str, Any]:
        """
        创建重构步骤。
        
        :param model_name: 模型名称
        :param result: 模型结果
        :return: 重构步骤的字典
        """
        return {
            "model": model_name,
            "action": "Refactor based on output",
            "details": result
        }

    def create_recommendation(self, model_name: str, result: Any) -> str:
        """
        创建重构建议。
        
        :param model_name: 模型名称
        :param result: 模型结果
        :return: 重构建议的字符串
        """
        return f"Consider refactoring using {model_name} output: {result}"

# 示例用法
if __name__ == "__main__":
    generator = RefactorPlanGenerator()
    sample_outputs = [
        {"model_name": "ModelA", "result": "Optimize function X"},
        {"model_name": "ModelB", "result": "Improve error handling"}
    ]
    plan = generator.generate_plan(sample_outputs)
    print(plan)