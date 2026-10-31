import json
import unittest
from unittest.mock import patch

from research_agent import research


class OpenAIPlannerTests(unittest.TestCase):
    def test_openai_request_uses_keychain_and_json_output(self):
        body = json.dumps(
            {
                "choices": [
                    {"message": {"content": '{"ideas": []}'}}
                ]
            }
        ).encode()
        with (
            patch.object(research, "load", return_value="hidden-openai-key") as load,
            patch.object(research, "json_request", return_value=(200, body, {})) as request,
        ):
            result = research._openai_json("plan", model="gpt-4.1-mini")

        self.assertEqual(result, '{"ideas": []}')
        load.assert_called_once_with(research.OPENAI_ACCOUNT)
        self.assertEqual(
            request.call_args.kwargs["headers"]["Authorization"],
            "Bearer hidden-openai-key",
        )
        self.assertEqual(
            request.call_args.kwargs["payload"]["response_format"],
            {"type": "json_object"},
        )

    def test_plan_rejects_repeated_milestones_and_unknown_sources(self):
        idea = {
            "name": "local-report-tool",
            "title": "Local Report Tool",
            "description": "Analyze local reports",
            "problem": "Reports take time to review",
            "approach": "Provide deterministic summaries",
            "milestones": ["same"] * 10,
            "source_urls": ["https://example.com/trend"],
        }
        ideas = [dict(idea, name=f"report-tool-{number}", title=f"Report Tool {number}")
                 for number in range(5)]
        with (
            patch.object(research, "_openai_json", return_value=json.dumps({"ideas": ideas})),
            self.assertRaisesRegex(research.ResearchError, "milestones"),
        ):
            research.select_projects(
                [{"url": "https://example.com/trend"}], model="test-model"
            )

        ideas = [
            dict(
                idea,
                name=f"report-tool-{number}",
                title=f"Report Tool {number}",
                milestones=[f"milestone {stage}" for stage in range(10)],
                source_urls=["https://not-in-results.example/source"],
            )
            for number in range(5)
        ]
        with (
            patch.object(research, "_openai_json", return_value=json.dumps({"ideas": ideas})),
            self.assertRaisesRegex(research.ResearchError, "cite trend research"),
        ):
            research.select_projects(
                [{"url": "https://example.com/trend"}], model="test-model"
            )


if __name__ == "__main__":
    unittest.main()
