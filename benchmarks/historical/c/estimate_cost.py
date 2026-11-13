import collections
import json
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PREVIOUS = Path("/tmp/billion-context-benchmark-20261106")
MILLION = Decimal(1_000_000)
LONG_THRESHOLD = 272_000
RATES = {"uncached_input": Decimal("10"), "cached_input": Decimal("1"), "cache_write": Decimal("12.5"), "output": Decimal("50")}
SOURCES = [
    "https://developers.openai.com/api/docs/models/gpt-6-astra",
    "https://developers.openai.com/api/docs/guides/prompt-caching",
    "https://developers.openai.com/api/docs/guides/reasoning",
    "https://learn.chatgpt.com/docs/pricing",
]


def samples(label):
    if label == "A":
        data = json.loads((PREVIOUS / "runs/A/metrics.json").read_text())
        return [{**row, "context_management": False} for row in data["otel_samples"]]
    run = (PREVIOUS if label == "B" else ROOT) / "runs" / label
    records = [json.loads(line) for line in (run / "audit/provider-usage.jsonl").read_text().splitlines()]
    context_ids = {row["id"] for row in records if row.get("kind") == "tool_call" and row.get("name") in ("compress", "decompress", "acp_status", "search_context")}
    by_request = {row["id"]: row for row in records if row.get("kind") == "usage"}
    response_ids = [row.get("response_id") for row in by_request.values()]
    assert len(response_ids) == len(set(response_ids))
    output = []
    for key, row in by_request.items():
        usage = row["usage"]
        output.append({
            "input_tokens": usage["input_tokens"],
            "cached_input_tokens": usage.get("input_tokens_details", {}).get("cached_tokens", 0),
            "cache_write_input_tokens": usage.get("input_tokens_details", {}).get("cache_write_tokens", 0),
            "output_tokens": usage["output_tokens"],
            "reasoning_output_tokens": usage.get("output_tokens_details", {}).get("reasoning_tokens", 0),
            "context_management": key in context_ids,
        })
    return output


def cost(row, long_rates=True):
    cached = row["cached_input_tokens"]
    writes = row["cache_write_input_tokens"]
    uncached = row["input_tokens"] - cached - writes
    assert uncached >= 0
    assert 0 <= row["reasoning_output_tokens"] <= row["output_tokens"]
    long_request = long_rates and row["input_tokens"] > LONG_THRESHOLD
    input_multiplier = Decimal(2 if long_request else 1)
    output_multiplier = Decimal("1.5") if long_request else Decimal(1)
    result = {
        "uncached_input": Decimal(uncached) * RATES["uncached_input"] * input_multiplier / MILLION,
        "cached_input": Decimal(cached) * RATES["cached_input"] * input_multiplier / MILLION,
        "cache_write": Decimal(writes) * RATES["cache_write"] * input_multiplier / MILLION,
        "output": Decimal(row["output_tokens"]) * RATES["output"] * output_multiplier / MILLION,
    }
    result["total"] = sum(result.values())
    return result


def aggregate(label, expected):
    data = samples(label)
    token_keys = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens", "reasoning_output_tokens")
    totals = {key: sum(row[key] for row in data) for key in token_keys}
    for key, total in totals.items():
        assert total == expected[key], (label, key, total, expected[key])
    costs = collections.defaultdict(Decimal)
    base_cost = Decimal(0)
    context_cost = Decimal(0)
    zero_output_cost = Decimal(0)
    for row in data:
        billed = cost(row)
        for key, value in billed.items():
            costs[key] += value
        base_cost += cost(row, long_rates=False)["total"]
        if row["context_management"]:
            context_cost += billed["total"]
        if row["output_tokens"] == 0:
            zero_output_cost += billed["total"]
    return {
        "measured_responses": len(data), "tokens": totals,
        "long_requests": sum(row["input_tokens"] > LONG_THRESHOLD for row in data),
        "long_request_input_tokens": sum(row["input_tokens"] for row in data if row["input_tokens"] > LONG_THRESHOLD),
        "standard_api_equivalent_usd": {key: str(value) for key, value in costs.items()},
        "without_long_context_uplift_usd": str(base_cost),
        "long_context_uplift_usd": str(costs["total"] - base_cost),
        "context_management_subset_usd": str(context_cost),
        "zero_output_reported_usage_usd": str(zero_output_cost),
        "sensitivity_if_all_zero_output_responses_unbilled_usd": str(costs["total"] - zero_output_cost),
    }


if __name__ == "__main__":
    comparison = json.loads((ROOT / "comparison-ABC.json").read_text())
    result = {
        "model": "gpt-6-astra", "currency": "USD", "speed_assumption": "Standard",
        "interpretation": "Current public API rates applied to reported usage, not an actual subscription invoice or included-limit deduction.",
        "rates_per_million": {key: str(value) for key, value in RATES.items()},
        "long_context": {"input_token_threshold_exclusive": LONG_THRESHOLD, "input_and_cache_multiplier": 2, "output_multiplier": "1.5", "scope": "entire qualifying request"},
        "sources": SOURCES,
        "arms": {label: aggregate(label, comparison["arms"][label]["reported_tokens"]) for label in "ABC"},
        "limits": [
            "Usage missing from cancelled or interrupted requests remains unknown and is excluded.",
            "No separate reasoning charge: reasoning is already inside output_tokens.",
            "Cache writes are a disjoint input category; observed write tokens are zero.",
            "No Fast, Flex/Batch, residency, tax or contract multiplier is assumed.",
            "Local tools were executed on the test machine, not OpenAI hosted tool containers.",
            "Zero-output sensitivity is not a finding that those requests are free; billing cannot be inferred from zero output alone."
        ],
    }
    (ROOT / "cost-estimate.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
