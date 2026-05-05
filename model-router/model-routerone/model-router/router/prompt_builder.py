class PromptBuilder:
    def __init__(self):
        self.prompts = {}

    def add_prompt(self, key, prompt):
        """Add a new prompt to the builder."""
        self.prompts[key] = prompt

    def get_prompt(self, key):
        """Retrieve a prompt by its key."""
        return self.prompts.get(key, None)

    def build_prompt(self, key, **kwargs):
        """Build a prompt by key, substituting any placeholders with provided arguments."""
        prompt = self.get_prompt(key)
        if prompt is None:
            raise ValueError(f"Prompt with key '{key}' not found.")
        return prompt.format(**kwargs)

    def list_prompts(self):
        """List all available prompts."""
        return list(self.prompts.keys())