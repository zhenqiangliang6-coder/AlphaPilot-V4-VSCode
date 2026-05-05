import unittest
from router.plan_generator import generate_refactor_plan

class TestPlanGenerator(unittest.TestCase):

    def test_generate_refactor_plan(self):
        # Test case for generating a refactor plan
        input_data = {
            "current_structure": "current_structure_example",
            "desired_structure": "desired_structure_example"
        }
        expected_output = {
            "steps": [
                "Step 1: Analyze current structure",
                "Step 2: Identify changes needed",
                "Step 3: Create a detailed plan"
            ]
        }
        
        result = generate_refactor_plan(input_data)
        self.assertEqual(result, expected_output)

    def test_generate_refactor_plan_empty_input(self):
        # Test case for handling empty input
        input_data = {}
        expected_output = {
            "error": "Input data is required to generate a refactor plan."
        }
        
        result = generate_refactor_plan(input_data)
        self.assertEqual(result, expected_output)

    def test_generate_refactor_plan_invalid_structure(self):
        # Test case for invalid structure input
        input_data = {
            "current_structure": None,
            "desired_structure": None
        }
        expected_output = {
            "error": "Invalid structure provided."
        }
        
        result = generate_refactor_plan(input_data)
        self.assertEqual(result, expected_output)

if __name__ == '__main__':
    unittest.main()