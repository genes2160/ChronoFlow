class BaseLLM:
    def generate(self, prompt: str):
        raise NotImplementedError

# ── Token estimation ────────────────────────────────────────────────────────
# FIX (Medium): removed duplicate estimate_tokens; kept the more accurate formula.
def estimate_tokens(text: str) -> int:
    return int(len(text) / 3.5)


# ── Provider limits ──────────────────────────────────────────────────────────
# FIX (High): moved PROVIDER_LIMITS above choose_provider_by_size so it is
# defined before it is referenced (previously caused NameError at import time).
PROVIDER_LIMITS = {
    "groq": 6000,        # safe for free tier TPM
    "openrouter": 40000, # large context free models
    "jina": 8000,        # embeddings / reader
    # "anthropic": 15000,  # depends on model, safe mid
}


# FIX (Low): choose_provider_by_size is now the single routing source of truth
# used inside run_llm_on_data, eliminating the duplicate inline logic.
def choose_provider_by_size(prompt_text: str) -> str:
    tokens = estimate_tokens(prompt_text)

    if tokens <= PROVIDER_LIMITS["groq"]:
        return "groq"

    if tokens <= PROVIDER_LIMITS["jina"]:
        return "jina"
    
    # if tokens <= PROVIDER_LIMITS["anthropic"]:
    #     return "anthropic"

    if tokens <= PROVIDER_LIMITS["openrouter"]:
        return "openrouter"

    return "openrouter"  # fallback for very large inputs

