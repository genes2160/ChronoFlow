# app/core/llm_config.py

LLM_CONFIG = {
    "default_provider": "openrouter",

    "providers": {
        "openrouter": {
            "api_key_setting": "OPENROUTER_API_KEY",
            "default_model": "openai/gpt-4o-mini",
        },
        "openai": {
            "api_key_setting": "OPENAI_API_KEY",
            "default_model": "gpt-4o-mini",
        },
        "anthropic": {
            "api_key_setting": "ANTHROPIC_API_KEY",
            "default_model": "claude-3-5-sonnet-20241022",
        },
        "grok": {
            "api_key_setting": "GROK_API_KEY",
            "default_model": "grok-2-latest",
        },
    }
}