import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from research_agent import cli


class DailyRunTests(unittest.TestCase):
    def test_runs_five_projects_sequentially_and_writes_report(self):
        ideas = [
            {"name": f"tool-{number}", "title": f"Tool {number}"}
            for number in range(5)
        ]
        with tempfile.TemporaryDirectory() as temporary:
            support = Path(temporary)
            calls = []

            def build(idea, *, model):
                calls.append(idea["name"])
                return {
                    "repository": f"https://github.com/jonfvk/{idea['name']}",
                    "checkout": f"/projects/{idea['name']}",
                    "commits": 10,
                }

            with (
                patch.object(cli, "_app_support", return_value=support),
                patch.object(cli.research, "search_trends", return_value=[{"title": "source", "url": "https://example.com", "published_date": "2026-10-30"}]),
                patch.object(cli.research, "select_projects", return_value=ideas),
                patch.object(cli, "build_project", side_effect=build),
            ):
                self.assertEqual(cli._run_batch("test-model"), 0)

            self.assertEqual(calls, [idea["name"] for idea in ideas])
            report_path = next(support.glob("*-run.json"))
            report = json.loads(report_path.read_text())
            self.assertEqual(report["status"], "completed")
            self.assertEqual(
                [item["status"] for item in report["projects"]],
                ["published"] * 5,
            )

    def test_refuses_duplicate_daily_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            support = Path(temporary)
            (support / f"{date.today().isoformat()}-run.json").write_text("{}")
            with (
                patch.object(cli, "_app_support", return_value=support),
                patch.object(cli.research, "search_trends") as search,
            ):
                self.assertEqual(cli._run_batch("test-model"), 1)
            search.assert_not_called()


if __name__ == "__main__":
    unittest.main()
