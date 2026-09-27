import unittest

from telemetry import (add_cost, aggregate_usage, anthropic_usage,
                       openai_usage, percentile, summarize_telemetry)


class UsageNormalizationTests(unittest.TestCase):
    def test_openai_usage_keeps_detail_tokens_within_reported_totals(self):
        usage = openai_usage({
            "prompt_tokens": 100,
            "completion_tokens": 40,
            "total_tokens": 140,
            "prompt_tokens_details": {"cached_tokens": 60},
            "completion_tokens_details": {"reasoning_tokens": 25},
        })
        self.assertEqual(usage, {
            "input_tokens": 100,
            "output_tokens": 40,
            "cached_tokens": 60,
            "reasoning_tokens": 25,
            "total_tokens": 140,
        })

    def test_anthropic_usage_combines_cached_and_uncached_input(self):
        usage = anthropic_usage({
            "input_tokens": 40,
            "cache_creation_input_tokens": 10,
            "cache_read_input_tokens": 50,
            "output_tokens": 20,
        })
        self.assertEqual(usage["input_tokens"], 100)
        self.assertEqual(usage["cached_tokens"], 60)
        self.assertEqual(usage["total_tokens"], 120)

    def test_cost_uses_configured_prices(self):
        usage = add_cost(
            {"input_tokens": 1_000_000, "output_tokens": 500_000},
            input_price=2,
            output_price=8,
        )
        self.assertEqual(usage["cost_usd"], 6.0)

    def test_aggregate_preserves_unavailable_fields(self):
        usage = aggregate_usage([
            {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            {"input_tokens": 20, "output_tokens": 7, "total_tokens": 27},
        ])
        self.assertEqual(usage["total_tokens"], 42)
        self.assertIsNone(usage["cached_tokens"])
        self.assertIsNone(usage["cost_usd"])


class TelemetrySummaryTests(unittest.TestCase):
    def test_p95_uses_linear_interpolation(self):
        self.assertAlmostEqual(percentile([0.1, 0.2, 0.3, 0.4], 0.95), 0.385)

    def test_summary_reports_request_latency_and_success_normalized_usage(self):
        results = [
            {
                "passed": True,
                "request_latencies": [0.1, 0.2],
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "total_tokens": 120,
                    "cost_usd": 0.012,
                },
            },
            {
                "passed": False,
                "request_latencies": [0.4],
                "usage": {
                    "input_tokens": 80,
                    "output_tokens": 10,
                    "total_tokens": 90,
                    "cost_usd": 0.008,
                },
            },
        ]
        summary = summarize_telemetry(results)
        self.assertEqual(summary["requests"], 3)
        self.assertEqual(summary["avg_latency_seconds"], 0.233)
        self.assertEqual(summary["p95_latency_seconds"], 0.38)
        self.assertEqual(summary["usage"]["total_tokens"], 210)
        self.assertEqual(summary["tokens_per_pass"], 210.0)
        self.assertEqual(summary["cost_per_pass_usd"], 0.02)

    def test_empty_telemetry_is_explicitly_unavailable(self):
        summary = summarize_telemetry([])
        self.assertEqual(summary["requests"], 0)
        self.assertIsNone(summary["p95_latency_seconds"])
        self.assertIsNone(summary["usage"])
        self.assertIsNone(summary["tokens_per_pass"])


if __name__ == "__main__":
    unittest.main()
