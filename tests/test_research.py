import json
import unittest
from unittest.mock import patch

from research_agent import research


class ResearchTests(unittest.TestCase):
    def test_tavily_search_uses_keychain_secret_and_bounds_recent_results(self):
        body = json.dumps(
            {
                "results": [
                    {
                        "title": "New developer tool",
                        "url": "https://example.com/tool",
                        "content": "A useful source snippet",
                        "published_date": "2026-10-30",
                    }
                ]
            }
        ).encode()
        with (
            patch.object(research, "load", return_value="hidden-key") as load,
            patch.object(research, "json_request", return_value=(200, body, {})) as request,
        ):
            results = research.search_trends()
        load.assert_called_once_with(research.TAVILY_ACCOUNT)
        self.assertEqual(results[0]["published_date"], "2026-10-30")
        self.assertEqual(request.call_args.args[0], "https://api.tavily.com/search")
        self.assertEqual(request.call_args.kwargs["payload"]["api_key"], "hidden-key")
        self.assertEqual(request.call_args.kwargs["payload"]["time_range"], "month")
        self.assertNotIn("hidden-key", str(results))

    def test_project_plan_requires_five_unique_ideas_and_ten_milestones(self):
        def idea(name):
            return {
                "name": name,
                "title": "Local Report Tool",
                "description": "Analyze local reports",
                "problem": "Reports take time to review",
                "approach": "Provide deterministic summaries",
                "milestones": [f"Milestone {n}" for n in range(10)],
                "source_urls": ["https://example.com/trend"],
            }
        ideas = [idea(f"local-report-tool-{n}") for n in range(5)]
        with patch.object(
            research, "_openai_json", return_value=json.dumps({"ideas": ideas})
        ):
            result = research.select_projects([], model="test-model")
        self.assertEqual(len(result), 5)

        ideas[0]["name"] = "bad slug"
        with patch.object(
            research, "_openai_json", return_value=json.dumps({"ideas": ideas})
        ):
            with self.assertRaises(research.ResearchError):
                research.select_projects([], model="test-model")

    def test_project_plan_rejects_wrong_count(self):
        with patch.object(
            research, "_openai_json", return_value=json.dumps({"ideas": []})
        ):
            with self.assertRaisesRegex(research.ResearchError, "exactly five"):
                research.select_projects([], model="test-model")


if __name__ == "__main__":
    unittest.main()
