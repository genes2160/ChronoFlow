from config import LLM_PROVIDER
from app.llm.anthropic import AnthropicLLM
from app.llm.openrouter import OpenRouterLLM
from app.llm.groq import GroqLLM
from app.llm.jina import JinaLLM
from app.utils import log


def get_llm():
    log("llm", f"Selecting provider: {LLM_PROVIDER}")

    if LLM_PROVIDER == "openrouter":
        log("llm", "Using OpenRouter")
        return OpenRouterLLM()

    if LLM_PROVIDER == "groq":
        log("llm", "Using Groq")
        return GroqLLM()

    if LLM_PROVIDER == "jina":
        log("llm", "Using Jina")
        return JinaLLM()

    if LLM_PROVIDER == "anthropic":
        log("llm", "Using Anthropic")
        return AnthropicLLM()

    log("error", f"Invalid provider: {LLM_PROVIDER}")
    raise ValueError("Invalid LLM provider")