"""GitHub REST API operations for the authenticated user."""

import json
import re
from typing import Any
from urllib.parse import quote

from research_agent.credentials import GITHUB_ACCOUNT, load
from research_agent.http import HTTPRequestError, json_request

_REPO_NAME = re.compile(r"^[A-Za-z0-9._-]{1,100}$")


class GitHubError(RuntimeError):
    """Sanitized GitHub API failure."""


def _api(path: str, *, method: str = "GET", payload: dict[str, Any] | None = None):
    token = load(GITHUB_ACCOUNT)
    try:
        status, body, _ = json_request(
            f"https://api.github.com{path}",
            method=method,
            headers={
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "Accept": "application/vnd.github+json",
            },
            payload=payload,
        )
    except HTTPRequestError as error:
        raise GitHubError(str(error)) from None
    try:
        result = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise GitHubError(f"GitHub returned an invalid response (HTTP {status}).") from None
    if status >= 400:
        message = result.get("message", "request rejected") if isinstance(result, dict) else "request rejected"
        raise GitHubError(f"GitHub API returned HTTP {status}: {message}")
    return status, result


def authenticated_login() -> str:
    status, user = _api("/user")
    if status != 200 or not isinstance(user.get("login"), str):
        raise GitHubError("GitHub did not return an authenticated account.")
    return user["login"]


def repository_exists(owner: str, name: str) -> bool:
    path = f"/repos/{quote(owner, safe='')}/{quote(name, safe='')}"
    try:
        _api(path)
        return True
    except GitHubError as error:
        if "HTTP 404" in str(error):
            return False
        raise


def create_public_repository(name: str, description: str) -> dict[str, str]:
    if not isinstance(name, str) or not _REPO_NAME.fullmatch(name) or name in {".", ".."}:
        raise ValueError("Repository name must be 1-100 letters, digits, dots, or dashes.")
    if len(description) > 350:
        raise ValueError("Description must be at most 350 characters.")
    status, repo = _api(
        "/user/repos",
        method="POST",
        payload={
            "name": name,
            "description": description,
            "private": False,
            "auto_init": False,
        },
    )
    if status != 201:
        raise GitHubError("GitHub did not confirm repository creation.")
    try:
        return {
            "full_name": repo["full_name"],
            "html_url": repo["html_url"],
            "clone_url": repo["clone_url"],
        }
    except (KeyError, TypeError):
        raise GitHubError("GitHub returned an incomplete repository response.") from None


def obtain_repository(name: str, description: str) -> dict[str, str]:
    """Create the repo, or reuse one of ours that is still empty from a failed run."""
    try:
        return create_public_repository(name, description)
    except GitHubError as error:
        if "HTTP 422" not in str(error):
            raise
    owner = authenticated_login()
    path = f"/repos/{quote(owner, safe='')}/{quote(name, safe='')}"
    _, repo = _api(path)
    try:
        _api(f"{path}/commits?per_page=1")
    except GitHubError as error:
        if "HTTP 409" not in str(error):
            raise
    else:
        raise GitHubError("Repository already exists and has commits; refusing to reuse it.")
    try:
        return {
            "full_name": repo["full_name"],
            "html_url": repo["html_url"],
            "clone_url": repo["clone_url"],
        }
    except (KeyError, TypeError):
        raise GitHubError("GitHub returned an incomplete repository response.") from None
