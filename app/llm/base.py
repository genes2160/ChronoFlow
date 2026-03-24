class BaseLLM:
    def generate(self, prompt: str):
        raise NotImplementedError