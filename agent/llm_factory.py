"""Build the browser-use chat model from LLM_MODEL / LLM_API_KEY env vars.

Default path is $0: a free Google AI Studio (Gemini) key.
Provider is picked from the model name; paid providers still work if you
later swap in a paid key and model.
"""
import os


def build_llm():
    model = os.environ.get("LLM_MODEL", "gemini-2.5-flash").strip()
    api_key = os.environ.get("LLM_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "LLM_API_KEY is not set. Get a free key at https://aistudio.google.com "
            "(Get API key) and put it in your .env file."
        )

    m = model.lower()

    # Google Gemini — the free default (AI Studio free tier, no credit card).
    if m.startswith("gemini") or m.startswith("gemma"):
        # google-genai SDK reads GEMINI_API_KEY from the environment.
        os.environ["GEMINI_API_KEY"] = api_key
        os.environ.setdefault("GOOGLE_API_KEY", api_key)
        from browser_use import ChatGoogle

        return ChatGoogle(model=model, api_key=api_key)

    # OpenAI
    if m.startswith(("gpt", "o1", "o3", "chatgpt")):
        os.environ["OPENAI_API_KEY"] = api_key
        from browser_use import ChatOpenAI

        return ChatOpenAI(model=model)

    # Anthropic
    if m.startswith("claude"):
        os.environ["ANTHROPIC_API_KEY"] = api_key
        from browser_use import ChatAnthropic

        return ChatAnthropic(model=model)

    # Browser-Use gateway (provider/model or bu-* ids), needs BROWSER_USE_API_KEY.
    if "/" in model or m.startswith("bu-"):
        os.environ["BROWSER_USE_API_KEY"] = api_key
        from browser_use import ChatBrowserUse

        return ChatBrowserUse(model=model)

    raise RuntimeError(
        f"Cannot determine an LLM provider for LLM_MODEL={model!r}. "
        "Use a gemini-*, gpt-*, claude-*, or provider/model id."
    )
