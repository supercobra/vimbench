"""Provider-neutral request telemetry for latency, token usage, and cost."""

from __future__ import annotations

import math

USAGE_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cached_tokens",
    "reasoning_tokens",
    "total_tokens",
)


def _integer(value):
    return int(value) if value is not None else None


def openai_usage(raw):
    """Normalize OpenAI-compatible usage fields.

    OpenAI includes cached tokens in ``prompt_tokens`` and reasoning tokens in
    ``completion_tokens``. The detail fields are therefore informational and
    must not be added to the total a second time.
    """
    if not raw:
        return None
    prompt_details = raw.get("prompt_tokens_details") or {}
    completion_details = raw.get("completion_tokens_details") or {}
    input_tokens = _integer(raw.get("prompt_tokens"))
    output_tokens = _integer(raw.get("completion_tokens"))
    total_tokens = _integer(raw.get("total_tokens"))
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_tokens": _integer(prompt_details.get("cached_tokens")),
        "reasoning_tokens": _integer(completion_details.get("reasoning_tokens")),
        "total_tokens": total_tokens,
    }


def anthropic_usage(raw):
    """Normalize Anthropic usage fields.

    Anthropic reports uncached input, cache creation, and cache reads as
    separate quantities. ``input_tokens`` here represents all input consumed.
    """
    if not raw:
        return None
    uncached = int(raw.get("input_tokens") or 0)
    cache_creation = int(raw.get("cache_creation_input_tokens") or 0)
    cache_read = int(raw.get("cache_read_input_tokens") or 0)
    output = _integer(raw.get("output_tokens"))
    input_tokens = uncached + cache_creation + cache_read
    return {
        "input_tokens": input_tokens,
        "output_tokens": output,
        "cached_tokens": cache_creation + cache_read,
        "reasoning_tokens": None,
        "total_tokens": input_tokens + output if output is not None else None,
    }


def add_cost(usage, input_price=None, output_price=None):
    """Add an estimated USD cost using prices per million tokens."""
    if not usage or input_price is None or output_price is None:
        return usage
    usage = dict(usage)
    usage["cost_usd"] = round(
        (usage.get("input_tokens") or 0) * float(input_price) / 1_000_000
        + (usage.get("output_tokens") or 0) * float(output_price) / 1_000_000,
        8,
    )
    return usage


def aggregate_usage(usages):
    """Sum observed usage while preserving unavailable fields as ``None``."""
    observed = [usage for usage in usages if usage]
    if not observed:
        return None
    totals = {}
    for field in USAGE_FIELDS:
        values = [usage[field] for usage in observed if usage.get(field) is not None]
        totals[field] = sum(values) if values else None
    costs = [usage["cost_usd"] for usage in observed
             if usage.get("cost_usd") is not None]
    totals["cost_usd"] = round(sum(costs), 8) if costs else None
    return totals


def percentile(values, quantile):
    """Return a linearly interpolated percentile (the R-7 method)."""
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def summarize_telemetry(results):
    """Aggregate request-level telemetry from single- or multi-turn results."""
    latencies = []
    usages = []
    for result in results:
        result_latencies = result.get("request_latencies")
        if result_latencies is None and result.get("latency_seconds") is not None:
            result_latencies = [result["latency_seconds"]]
        latencies.extend(result_latencies or [])
        if result.get("usage"):
            usages.append(result["usage"])

    usage = aggregate_usage(usages)
    passed = sum(bool(result.get("passed")) for result in results)
    summary = {
        "requests": len(latencies),
        "avg_latency_seconds": (round(sum(latencies) / len(latencies), 3)
                                if latencies else None),
        "p95_latency_seconds": (round(percentile(latencies, 0.95), 3)
                                if latencies else None),
        "usage": usage,
        "tokens_per_pass": None,
        "cost_per_pass_usd": None,
    }
    if passed and usage:
        if usage.get("total_tokens") is not None:
            summary["tokens_per_pass"] = round(usage["total_tokens"] / passed, 1)
        if usage.get("cost_usd") is not None:
            summary["cost_per_pass_usd"] = round(usage["cost_usd"] / passed, 8)
    return summary
