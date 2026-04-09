from config import LLM_PROVIDER
from app.llm.anthropic import AnthropicLLM
from app.llm.openrouter import OpenRouterLLM
from app.llm.groq import GroqLLM
from app.llm.jina import JinaLLM
from app.utils import log


def get_llm(llm_provider=LLM_PROVIDER):
    log("llm", f"Selecting provider: {llm_provider}")

    if llm_provider == "openrouter":
        log("llm", "Using OpenRouter")
        return OpenRouterLLM()

    if llm_provider == "groq":
        log("llm", "Using Groq")
        return GroqLLM()

    if llm_provider == "jina":
        log("llm", "Using Jina")
        return JinaLLM()

    if llm_provider == "anthropic":
        log("llm", "Using Anthropic")
        return AnthropicLLM()

    log("error", f"Invalid provider: {llm_provider}")
    raise ValueError("Invalid LLM provider")