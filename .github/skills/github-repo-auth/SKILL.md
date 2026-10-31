---
name: github-repo-auth
description: 'Use Research Agent macOS Keychain credentials to verify GitHub identity and create a separate public repository through the REST API over verified TLS 1.2. Use for repository creation and publishing.'
---

# GitHub authentication

Research Agent does not depend on `gh auth status`. Its GitHub API client pins
TLS 1.2 while preserving certificate verification, and its Git transport uses
the macOS Keychain credential helper.

Check or migrate credentials:

```sh
.venv/bin/python -m research_agent.cli credentials status
.venv/bin/python -m research_agent.cli credentials migrate
```

The migration copies existing Research Agent setup entries from the legacy
Codex-AgentBuild Keychain service, verifies the copied credentials, and leaves
the source entries unchanged.

For fresh setup:

```sh
.venv/bin/python -m research_agent.cli credentials setup
```

Use a GitHub classic PAT with `public_repo` scope for creating and pushing
public repositories. Never place credentials in shell arguments, URLs, source,
`.env` files, logs, or chat. Do not retry with certificate verification
disabled.
