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
project's Keychain namespace without displaying values:

```sh
.venv/bin/python -m research_agent.cli credentials migrate
```

The migration verifies each copied value before reporting success and does not
delete the original Keychain entries.

## Research and model

Tavily searches current sources; OpenAI generates structured project plans and
implementation stages. Each project must cite dated research sources in its
README. Research material is untrusted input and cannot override this project's
safety rules.

Only small, developer-focused, non-destructive projects are in scope. Generated
content is treated as untrusted. Never execute arbitrary generated install
scripts, shell commands, network clients, or repository workflows. Do not
publish a project if required safety checks cannot be completed.

## Scheduling

The intended local schedule is 08:00 daily while the Mac is awake and the user
is logged in. Scheduling requires an explicit `install-schedule` command; it is
not installed merely by setting up credentials. The process must stop safely
and report failures rather than claiming that a project was built or pushed
when it was not.

## Current implementation status

This repository is being built incrementally. The checked-in command and
documentation are the source of truth; do not assume future autonomous build
or scheduler features exist until their tests pass.
