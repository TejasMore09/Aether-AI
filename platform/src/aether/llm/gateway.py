"""LLM gateway: every model call in the platform goes through here.

Responsibilities:
  - provider-agnostic completion via LiteLLM (swap models by config, not code)
  - per-tenant metering: tokens + cost recorded in llm_usage (RLS-scoped)
  - per-tenant monthly budget enforcement — over budget means the caller gets
    a clean "denied" result and falls back; never a silent overspend
  - failure containment: network/provider errors come back as a result
    object, never an exception into workflow code

No prompt content is ever stored — only metadata (model, tokens, cost).
"""

import datetime
import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select

from aether.core.config import get_settings
from aether.core.db import tenant_session
from aether.core.models import LLMUsage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMResult:
    ok: bool
    text: str = ""
    error: str = ""  # "" | "budget_exceeded" | provider error summary
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0


def _month_start() -> datetime.datetime:
    now = datetime.datetime.now(datetime.UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def month_spend_usd(tenant_id: uuid.UUID) -> float:
    with tenant_session(tenant_id) as db:
        total = db.scalar(
            select(func.coalesce(func.sum(LLMUsage.cost_usd), 0.0)).where(
                LLMUsage.created_at >= _month_start()
            )
        )
        return float(total or 0.0)


def complete(
    tenant_id: uuid.UUID,
    messages: list[dict],
    purpose: str,
) -> LLMResult:
    """Run one chat completion for a tenant, metered and budget-checked."""
    settings = get_settings()

    spent = month_spend_usd(tenant_id)
    if spent >= settings.llm_monthly_budget_usd_per_tenant:
        logger.warning(
            "LLM budget exhausted for tenant=%s (spent=%.4f, budget=%.2f)",
            tenant_id,
            spent,
            settings.llm_monthly_budget_usd_per_tenant,
        )
        return LLMResult(ok=False, error="budget_exceeded")

    try:
        import litellm

        response = litellm.completion(
            model=settings.llm_model,
            messages=messages,
            timeout=settings.llm_timeout_seconds,
            max_tokens=settings.llm_max_output_tokens,
            temperature=settings.llm_temperature,
            # None rather than "" so LiteLLM falls back to its own environment
            # lookup when nothing is configured here.
            api_key=settings.llm_api_key or None,
        )
        choice = response.choices[0]
        text = (choice.message.content or "").strip()
        finish = getattr(choice, "finish_reason", None)
        usage = getattr(response, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        try:
            cost = float(litellm.completion_cost(completion_response=response) or 0.0)
        except Exception:
            cost = 0.0
    except Exception as exc:  # provider/network failure — contained here
        logger.error("LLM call failed (purpose=%s): %s", purpose, exc)
        return LLMResult(ok=False, error=f"provider_error: {type(exc).__name__}")

    # A truncated answer is worse than no answer, and it does not look like a
    # failure: `text` is non-empty and nothing raised, so without this check
    # the caller stores it and a customer reads two sentences that stop
    # mid-number. The deterministic fallback is less impressive and complete,
    # which is the right trade. Metered anyway — the tokens were spent.
    truncated = finish == "length"
    if truncated:
        logger.error(
            "LLM answer truncated (purpose=%s, completion_tokens=%s, cap=%s) — "
            "reasoning models spend this budget before writing anything visible",
            purpose,
            completion_tokens,
            settings.llm_max_output_tokens,
        )

    with tenant_session(tenant_id) as db:
        db.add(
            LLMUsage(
                tenant_id=tenant_id,
                purpose=purpose,
                model=settings.llm_model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=cost,
            )
        )

    if truncated:
        return LLMResult(ok=False, error="truncated", model=settings.llm_model)

    return LLMResult(
        ok=True,
        text=text,
        model=settings.llm_model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost,
    )
