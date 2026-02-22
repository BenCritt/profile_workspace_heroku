import functools

# Update this date whenever you manually verify pricing against official provider pages.
PRICING_LAST_VERIFIED = "2026-02-21"

# Human-readable labels for each task_type value. Used by the template to annotate
# the estimated output token count with its source heuristic.
TASK_LABELS = {
    "summarize":  "Summarize (≈15% of input, min. 150)",
    "translate":  "Translate (≈100% of input)",
    "code":       "Code Refactor (≈120% of input)",
    "classify":   "Classify (150 tokens fixed)",
    "generate":   "Generate (≈50% of input, 500–4,000)",
}

@functools.lru_cache(maxsize=1)
def get_tiktoken_encoding():
    """
    Caches the tiktoken encoding object in memory so it only loads once per
    Gunicorn worker, preventing repeated disk I/O on every form submission.
    """
    import tiktoken
    return tiktoken.get_encoding("cl100k_base")


def estimate_tokens_and_cost(text, task_type="summarize"):
    """
    Estimates the number of tokens in a given text and calculates the total API
    cost (input + output) across several popular LLMs.

    Token counting uses OpenAI's cl100k_base encoding via tiktoken, which is a
    close approximation for current OpenAI models and a reasonable heuristic for
    Anthropic and Google models. Actual token counts will vary slightly per
    provider due to differing tokenization schemes.
    """
    character_count = len(text)

    try:
        encoding = get_tiktoken_encoding()
        token_count = len(encoding.encode(text))
        # Surface the tokenizer name so the template can display the disclaimer.
        calculation_method = "tiktoken cl100k_base"
    except ImportError:
        # Fallback heuristic if tiktoken is not installed: ~4 characters per token.
        token_count = max(1, int(character_count / 4))
        calculation_method = "Estimated (~4 chars/token)"

    # Standard per-million token pricing (USD).
    # pricing_url is surfaced in the template so users can verify before committing.
    models = [
        {
            "name": "Claude Sonnet 4.6",
            "provider": "Anthropic",
            "in_cost":  3.00,
            "out_cost": 15.00,
            "pricing_url": "https://www.anthropic.com/pricing#api",
        },
        {
            "name": "Claude Opus 4.6",
            "provider": "Anthropic",
            "in_cost":  15.00,
            "out_cost": 75.00,
            "pricing_url": "https://www.anthropic.com/pricing#api",
        },
        {
            "name": "GPT-5.2",
            "provider": "OpenAI",
            "in_cost":  1.75,
            "out_cost": 14.00,
            "pricing_url": "https://openai.com/api/pricing/",
        },
        {
            "name": "Gemini 3.1 Pro",
            "provider": "Google",
            "in_cost":  1.25,
            "out_cost": 10.00,
            "pricing_url": "https://ai.google.dev/pricing",
        },
    ]

    # --- Output token estimation ---
    # Each heuristic is documented with its rationale. Floors and caps prevent
    # nonsensical results at the extremes of very short or very large inputs.
    if task_type == "summarize":
        # Summaries are much shorter than source text. Floor at 150 tokens to
        # account for structural overhead (intro, body, closing) even on tiny inputs.
        # Cap at 2,000 tokens — even long-document summaries rarely exceed this.
        estimated_output_tokens = max(150, min(int(token_count * 0.15), 2000))

    elif task_type == "translate":
        # Translation preserves content volume; output ≈ input length.
        estimated_output_tokens = max(50, int(token_count * 1.0))

    elif task_type == "code":
        # Refactoring typically produces slightly more code than it receives
        # due to added comments, type hints, and restructuring.
        estimated_output_tokens = max(100, int(token_count * 1.2))

    elif task_type == "classify":
        # Fixed: assumes label + confidence score + 1–2 sentence rationale.
        # A bare label is 1–5 tokens; including brief explanation lands ~150.
        estimated_output_tokens = 150

    elif task_type == "generate":
        # Content generation scales with context size, but plateaus — the model
        # won't output 50K tokens just because you gave it 50K tokens of context.
        # Floor at 500 (short prompts still produce a full piece).
        # Cap at 4,000 (a realistic long-form article or report ceiling).
        estimated_output_tokens = max(500, min(int(token_count * 0.50), 4000))

    else:
        # Unknown task_type: generic fallback.
        estimated_output_tokens = 500

    # Build the per-model cost breakdown.
    for model in models:
        in_calc    = (token_count            / 1_000_000) * model["in_cost"]
        out_calc   = (estimated_output_tokens / 1_000_000) * model["out_cost"]
        total_calc = in_calc + out_calc

        model["in_rate_display"]   = f"${model['in_cost']:.2f}"
        model["out_rate_display"]  = f"${model['out_cost']:.2f}"
        model["in_cost_display"]   = f"${in_calc:,.6f}"
        model["out_cost_display"]  = f"${out_calc:,.6f}"
        model["total_cost_display"]= f"${total_calc:,.6f}"

    return {
        "character_count":      f"{character_count:,}",
        "token_count":          f"{token_count:,}",
        "output_tokens":        f"{estimated_output_tokens:,}",
        "task_label":           TASK_LABELS.get(task_type, "Unknown"),
        "calculation_method":   calculation_method,
        "pricing_last_verified":PRICING_LAST_VERIFIED,
        "models":               models,
    }