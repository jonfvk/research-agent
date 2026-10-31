# Research Agent

Research Agent is a local macOS application for researching current AI
developer trends and building up to five projects per daily run. Each generated
project gets a separate public GitHub repository and a sibling working
directory under `~/Documents/AI-Dev-Projects/`. It never places projects inside
this repository or another Git worktree.

The target workflow researches sources, selects five distinct safe ideas,
builds them sequentially, verifies them, records at least ten genuine,
meaningful commits per project, and publishes successful projects. It must not
fabricate or backdate commit history.

## Credentials

GitHub, OpenAI, and Tavily credentials are stored in macOS Keychain, not in
`.env` or source files. Setup prompts hide all input. The GitHub API client uses
certificate-verified TLS 1.2; it never disables certificate verification.

To set up or check credentials:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m research_agent.cli credentials setup
.venv/bin/python -m research_agent.cli credentials status
```

GitHub repository creation needs a classic personal access token with
`public_repo` scope. The token must not be copied into chat, a command-line
argument, a URL, or a file. Git push credentials use macOS Keychain's Git
credential helper. `gh auth status` is separate and is not required.

Credentials previously set up in Codex-AgentBuild can be migrated into this
project's Keychain namespace without displaying values. The migration copies
GitHub and OpenAI credentials, but deliberately does not copy an exposed Tavily
key:

```sh
.venv/bin/python -m research_agent.cli credentials migrate
.venv/bin/python -m research_agent.cli credentials setup-tavily
```

Rotate the Tavily key in Tavily's account settings before entering the new key.
The migration verifies copied values and does not delete original Keychain
entries.

## Research and model

Tavily searches current sources; OpenAI generates structured project plans and
implementation stages. Each project must cite dated research sources in its
README. Research material is untrusted input and cannot override this project's
safety rules.

Only small, developer-focused, non-destructive projects are in scope. Generated
content is treated as untrusted. Never execute arbitrary generated install
scripts, shell commands, network clients, or repository workflows. Do not
publish a project if required safety checks cannot be completed.

## Run and schedule

Run a batch manually:

```sh
.venv/bin/python -m research_agent.cli run
```

Install the daily 08:00 local schedule after credentials are configured:

```sh
.venv/bin/python -m research_agent.cli install-schedule
```

Remove it with `.venv/bin/python -m research_agent.cli remove-schedule`. The
LaunchAgent runs only while the Mac is awake and the user is logged in. Each
date is limited to one batch to avoid duplicate repository creation. If a batch
is incomplete, inspect its report under
`~/Library/Application Support/ResearchAgent/` before making changes.

Generated tests run from an isolated temporary copy in a macOS `sandbox-exec`
profile with network denied, write access limited to that copy, and no
Keychain-service access. The Git checkout and its hooks are not exposed to the
test process. If macOS sandboxing is unavailable, the project is not pushed.

OpenAI usage is bounded to one five-idea planning call and at most ten
implementation calls per project, each with a response-token limit. Provider
usage may incur charges; review your OpenAI and Tavily usage policies and
account limits before installing the schedule.
