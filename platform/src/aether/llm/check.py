"""Is the model key actually reaching the process?

    python -m aether.llm.check

Exists because getting this wrong fails quietly. A missing or wrong key does
not raise: the diagnosis layer falls back to its deterministic generator, the
product keeps working, and every explanation is simply worse than it should be
with nothing in the logs that names the cause. Someone can run in that state
for weeks.

So this answers the question directly, and separates the three ways it can go
wrong — no key configured, a key the provider rejects, and a model name the
key cannot reach — because the fix differs for each.

It sends one very small completion, which costs a fraction of a cent.
"""

from __future__ import annotations

import sys

from aether.core.config import get_settings


def main() -> int:
    settings = get_settings()
    key = settings.llm_api_key
    model = settings.llm_model

    if key:
        where = f"AETHER_LLM_API_KEY  ({key[:6]}…{key[-4:]}, {len(key)} chars)"
    else:
        import os

        env_key = os.environ.get("GEMINI_API_KEY", "")
        if env_key:
            where = f"GEMINI_API_KEY in the environment  ({env_key[:6]}…{env_key[-4:]})"
        else:
            print("NO KEY. AETHER_LLM_API_KEY is empty in platform/.env and")
            print("GEMINI_API_KEY is not set in the environment either.")
            print("\nEvery diagnosis is falling back to the deterministic generator.")
            return 1

    print(f"key    : {where}")
    print(f"model  : {model}")
    print("calling the provider…\n")

    try:
        import litellm

        response = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": "Reply with exactly: ok"}],
            max_tokens=settings.llm_max_output_tokens,
            temperature=settings.llm_temperature,
            api_key=key or None,
        )
    except Exception as exc:  # noqa: BLE001 - this command exists to report it
        print(f"FAILED: {type(exc).__name__}")
        print(f"  {exc}")
        print("\nA rejected key and an unreachable model look similar here — read the")
        print("message above: 'API key not valid' is the key, 'not found' is the model.")
        return 1

    choice = response.choices[0]
    text = (choice.message.content or "").strip()
    usage = response.usage
    thinking = getattr(getattr(usage, "completion_tokens_details", None), "reasoning_tokens", 0)

    print(f"OK. replied {text!r}")
    print(
        f"  finish={choice.finish_reason}  prompt={usage.prompt_tokens} "
        f"completion={usage.completion_tokens} (thinking={thinking})"
    )

    if choice.finish_reason == "length":
        # The failure that produced two-sentence explanations for weeks: a
        # reasoning model spends the output budget before writing anything.
        print(
            f"\nWARNING: truncated even on a trivial prompt. "
            f"AETHER_LLM_MAX_OUTPUT_TOKENS is {settings.llm_max_output_tokens}, "
            f"which this model cannot finish within. Real diagnoses will all "
            f"fall back."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
