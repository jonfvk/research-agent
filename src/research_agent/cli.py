"""Command-line entry point for Research Agent."""

import argparse
from datetime import date
import fcntl
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys

from research_agent import credentials, github, research
from research_agent.builder import BuildError, build_project

LABEL = "com.jonfvk.research-agent"
PROJECTS_PER_BATCH = 5
MAX_BATCHES = 4
TOPICS = [
    "AI developer tools coding agents",
    "LLM evaluation testing observability",
    "AI agent frameworks MCP tooling",
    "developer productivity documentation code review AI",
]


def _app_support() -> Path:
    path = Path.home() / "Library" / "Application Support" / "ResearchAgent"
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def _run_batch(model: str, batches: int = 1) -> int:
    total = batches * PROJECTS_PER_BATCH
    lock_path = _app_support() / "run.lock"
    with lock_path.open("a") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("A Research Agent batch is already running.", file=sys.stderr)
            return 1

        report_path = _app_support() / f"{date.today().isoformat()}-run.json"
        if report_path.exists():
            print(
                f"A run record already exists for today: {report_path}. "
                "Inspect it before attempting a retry.",
                file=sys.stderr,
            )
            return 1

        report = {
            "date": date.today().isoformat(),
            "status": "in_progress",
            "sources": [],
            "projects": [],
        }
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        projects_dir = Path.home() / "Documents" / "AI-Dev-Projects"
        used: set[str] = (
            {item.name for item in projects_dir.iterdir()} if projects_dir.is_dir() else set()
        )
        for batch in range(batches):
            print(f"Searching current AI developer trends (batch {batch + 1}/{batches})...")
            try:
                sources = research.search_trends(topic=TOPICS[batch % len(TOPICS)])
                ideas = research.select_projects(sources, model=model, avoid=used)
            except research.ResearchError as error:
                print(f"Batch {batch + 1} planning failed: {error}", file=sys.stderr)
                break
            report["sources"] += [
                {"title": s["title"], "url": s["url"], "published_date": s["published_date"]}
                for s in sources
            ]
            for idea in ideas[:PROJECTS_PER_BATCH]:
                used.add(idea["name"])
                entry = {"name": idea["name"], "title": idea["title"], "status": "building"}
                report["projects"].append(entry)
                report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
                print(f"[{len(report['projects'])}/{total}] Building {idea['name']}...")
                try:
                    result = build_project(idea, model=model)
                    entry.update(
                        status="published",
                        repository=result["repository"],
                        checkout=result["checkout"],
                        commits=result["commits"],
                    )
                    print(f"Published {result['repository']} ({result['commits']} commits).")
                except (
                    BuildError,
                    github.GitHubError,
                    research.ResearchError,
                    OSError,
                    ValueError,
                ) as error:
                    entry.update(status="failed", error=str(error)[:500])
                    print(f"{idea['name']} did not complete: {error}", file=sys.stderr)
                report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        report["status"] = (
            "completed"
            if len(report["projects"]) == total
            and all(item["status"] == "published" for item in report["projects"])
            else "incomplete"
        )
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Run {report['status']}. Report: {report_path}")
        return 0 if report["status"] == "completed" else 1


def install_schedule() -> int:
    if sys.platform != "darwin":
        print("Daily scheduling is supported only on macOS.", file=sys.stderr)
        return 1
    status = credentials.status()
    if not all(status.values()):
        print("Set up GitHub, OpenAI, and Tavily credentials before scheduling.", file=sys.stderr)
        return 1
    logs = Path.home() / "Library" / "Logs" / "ResearchAgent"
    logs.mkdir(parents=True, exist_ok=True, mode=0o700)
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "Label": LABEL,
        "ProgramArguments": [
            sys.executable,
            "-m",
            "research_agent.cli",
            "run",
            "--model",
            "gpt-4.1-mini",
        ],
        "StartCalendarInterval": {"Hour": 8, "Minute": 0},
        "RunAtLoad": False,
        "StandardOutPath": str(logs / "stdout.log"),
        "StandardErrorPath": str(logs / "stderr.log"),
        "EnvironmentVariables": {
            "PYTHONNOUSERSITE": "1",
            "PATH": os.path.dirname(sys.executable),
        },
    }
    plist_path.write_bytes(plistlib.dumps(document))
    subprocess.run(
        ["launchctl", "bootstrap", f"gui/{os.getuid()}", str(plist_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    print(f"Installed daily 08:00 LaunchAgent: {plist_path}")
    print("Runs only while this Mac is awake and your user session is logged in.")
    return 0


def remove_schedule() -> int:
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    subprocess.run(
        ["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if plist_path.exists():
        plist_path.unlink()
    print("Research Agent daily schedule removed.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Research trends and build separate GitHub projects.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    credential_parser = subparsers.add_parser("credentials")
    credential_sub = credential_parser.add_subparsers(dest="credential_command", required=True)
    credential_sub.add_parser("setup")
    credential_sub.add_parser("setup-tavily")
    credential_sub.add_parser("status")
    credential_sub.add_parser("migrate")

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--model", default="gpt-4.1-mini")
    run_parser.add_argument("--batches", type=int, default=1, choices=range(1, MAX_BATCHES + 1),
                            help="Batches of five projects (4 = 20 projects)")
    subparsers.add_parser("install-schedule")
    subparsers.add_parser("remove-schedule")

    args = parser.parse_args(argv)
    try:
        if args.command == "credentials":
            if args.credential_command == "setup":
                login = credentials.setup(github.authenticated_login)
                credentials.store_git_credential(
                    login, credentials.load(credentials.GITHUB_ACCOUNT)
                )
                print(f"Stored credentials in macOS Keychain; GitHub account verified: {login}")
                return 0
            if args.credential_command == "status":
                configured = credentials.status()
                for name, present in configured.items():
                    print(f"{name}: {'configured' if present else 'not configured'}")
                if configured["github"]:
                    print(f"github account: {github.authenticated_login()}")
                return 0
            if args.credential_command == "setup-tavily":
                credentials.setup_tavily()
                print("New Tavily credential stored in macOS Keychain.")
                return 0
            if args.credential_command == "migrate":
                migrated = credentials.migrate_legacy_credentials(
                    exclude_accounts={credentials.TAVILY_ACCOUNT}
                )
                for name, present in migrated.items():
                    if name == "tavily":
                        message = "fresh rotated key required"
                    else:
                        message = "migrated or already configured" if present else "not available"
                    print(f"{name}: {message}")
                if not migrated["github"] or not migrated["openai"]:
                    return 1
                login = github.authenticated_login()
                credentials.store_git_credential(
                    login, credentials.load(credentials.GITHUB_ACCOUNT)
                )
                print(f"Verified GitHub account: {login}. Original Keychain entries remain unchanged.")
                return 0
        if args.command == "run":
            if not all(credentials.status().values()):
                print("GitHub, OpenAI, and Tavily credentials are required.", file=sys.stderr)
                return 1
            return _run_batch(args.model, args.batches)
        if args.command == "install-schedule":
            return install_schedule()
        if args.command == "remove-schedule":
            return remove_schedule()
    except (credentials.CredentialError, github.GitHubError, research.ResearchError) as error:
        print(str(error), file=sys.stderr)
        return 1
    except subprocess.CalledProcessError:
        print("LaunchAgent operation failed; inspect launchd status.", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
