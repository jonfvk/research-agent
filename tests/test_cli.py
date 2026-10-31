import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
import plistlib
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


class ScheduleTests(unittest.TestCase):
    def test_schedule_installs_daily_at_0800_only_after_credentials(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            with (
                patch.object(cli.credentials, "status", return_value={"github": True, "openai": True, "tavily": True}),
                patch.object(cli.Path, "home", return_value=home),
                patch.object(cli.sys, "executable", "/test/venv/bin/python"),
                patch.object(cli.subprocess, "run") as run,
            ):
                self.assertEqual(cli.install_schedule(), 0)

            plist = home / "Library" / "LaunchAgents" / f"{cli.LABEL}.plist"
            document = plistlib.loads(plist.read_bytes())
            self.assertEqual(document["StartCalendarInterval"], {"Hour": 8, "Minute": 0})
            self.assertFalse(document["RunAtLoad"])
            self.assertEqual(document["ProgramArguments"][:3], [
                "/test/venv/bin/python", "-m", "research_agent.cli"
            ])
            run.assert_called_once()

    def test_schedule_refuses_when_keys_missing(self):
        with (
            patch.object(cli.credentials, "status", return_value={"github": True, "openai": False, "tavily": True}),
            patch.object(cli.subprocess, "run") as run,
        ):
            self.assertEqual(cli.install_schedule(), 1)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
