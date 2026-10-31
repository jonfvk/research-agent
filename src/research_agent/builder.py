"""Build each trend project in an isolated sibling Git repository."""

import ast
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile

from research_agent.github import obtain_repository
from research_agent.research import implementation_stage

_REPO = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_COMMIT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._():/-]{0,71}$")
_PYTHON_FILE = re.compile(r"^(?:[a-z][a-z0-9_]*|__init__)\.py$")
_SECRET = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|tvly-[A-Za-z0-9_-]{16,})"
)
_BLOCKED_MODULES = {
    "subprocess", "socket", "http", "urllib3", "requests", "httpx", "aiohttp",
    "pickle", "marshal", "keyring", "dotenv", "ctypes", "importlib", "ftplib",
    "smtplib", "telnetlib", "xmlrpc", "multiprocessing", "pty",
}
_BLOCKED_CALLS = {"eval", "exec", "compile", "__import__", "open_url"}
_BLOCKED_ATTRS = {"system", "popen", "spawn", "urlopen", "urlretrieve", "rmtree"}


def _third_party_import(tree: ast.AST, local: frozenset[str]) -> str | None:
    allowed = set(sys.stdlib_module_names) | set(local)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and not node.level:
            names = [node.module or ""]
        else:
            continue
        for name in names:
            if name.split(".")[0] not in allowed:
                return name
    return None


def _blocked_reason(tree: ast.AST) -> str | None:
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
            if node.module == "urllib" and any(a.name == "request" for a in node.names):
                return "urllib.request"
        for name in names:
            if name.split(".")[0] in _BLOCKED_MODULES or name == "urllib.request":
                return name
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in _BLOCKED_CALLS:
                return func.id
            if isinstance(func, ast.Attribute) and func.attr in _BLOCKED_ATTRS:
                return func.attr
    return None


def _clean_commit_message(raw: str) -> str:
    line = raw.strip().splitlines()[0] if raw.strip() else ""
    line = re.sub(r"[^A-Za-z0-9 ._():/-]", " ", line)
    line = re.sub(r"\s+", " ", line).strip()[:72].strip()
    return line


class BuildError(RuntimeError):
    """Project build stopped without claiming a successful publication."""


class TestFailure(BuildError):
    __test__ = False

    def __init__(self, message: str, output: str):
        super().__init__(message)
        self.output = output


def _git(directory: Path, *args: str, env: dict | None = None) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(directory), *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
    except (OSError, subprocess.SubprocessError) as error:
        detail = getattr(error, "stderr", "") or ""
        if any(secret in detail for secret in ("ghp_", "github_pat_", "sk-", "tvly-")):
            detail = ""
        safe = detail.strip().splitlines()[-1][:300] if detail.strip() else "git operation failed"
        raise BuildError(safe) from None
    return result.stdout.strip()


def _allowed_path(raw_path: str) -> Path:
    if not isinstance(raw_path, str) or "\\" in raw_path or "\x00" in raw_path:
        raise BuildError("Generated file path is invalid.")
    path = PurePosixPath(raw_path)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise BuildError("Generated file path escapes the project root.")
    allowed = (
        path.as_posix() in {"README.md", "pyproject.toml", ".gitignore"}
        or (
            len(path.parts) == 3
            and path.parts[0] == "src"
            and re.fullmatch(r"[a-z][a-z0-9_]*", path.parts[1])
            and _PYTHON_FILE.fullmatch(path.name)
        )
        or (
            len(path.parts) == 2
            and path.parts[0] == "tests"
            and path.name.startswith("test_")
            and _PYTHON_FILE.fullmatch(path.name)
        )
        or (len(path.parts) == 2 and path.parts[0] == "docs" and path.suffix == ".md")
    )
    if not allowed:
        raise BuildError(
            f"Path '{raw_path}' is not allowed. Use exactly one of: README.md, pyproject.toml, "
            ".gitignore, src/<package>/<file>.py (no subfolders), tests/test_<name>.py "
            "(no subfolders, no conftest.py), docs/<name>.md."
        )
    return Path(*path.parts)


def _validate_content(path: Path, content: str, local: frozenset[str] = frozenset({"src"})) -> None:
    if not isinstance(content, str) or not content.strip() or len(content.encode()) > 80_000:
        raise BuildError("Generated file is empty or exceeds the size limit.")
    if re.search(r"(?i)(?:api[_-]?key|secret[_-]?key|password)\s*=\s*['\"][^'\"]{8,}", content):
        raise BuildError("Generated file appears to contain a hard-coded secret.")
    if path.suffix == ".py":
        try:
            tree = ast.parse(content)
        except SyntaxError:
            raise BuildError("Generated Python file has a syntax error.") from None
        outside = _third_party_import(tree, local)
        if outside:
            raise BuildError(
                f"Import of '{outside}' is not allowed: only the Python standard library "
                "and this project's own modules are installed. Do not use third-party packages."
            )
        reason = _blocked_reason(tree)
        if reason or _SECRET.search(content):
            raise BuildError(
                f"Generated file uses a disallowed execution, network, or credential pattern ({reason or 'secret'})."
            )


def _read_existing(root: Path, limit: int = 3000) -> list[dict[str, str]]:
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or ".git" in path.parts:
            continue
        if path.suffix not in {".py", ".md", ".toml"} and path.name != ".gitignore":
            continue
        files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "content": path.read_text(encoding="utf-8")[:limit],
            }
        )
    return files


def _safe_test(root: Path) -> str:
    sandbox_exec = shutil.which("sandbox-exec")
    if sys.platform != "darwin" or sandbox_exec is None:
        raise BuildError("A macOS sandbox is required; generated tests were not run.")
    interpreter = Path(sys.base_prefix) / "bin" / f"python{sys.version_info.major}.{sys.version_info.minor}"
    if not interpreter.is_file():
        raise BuildError("A direct Python interpreter is required; generated tests were not run.")
    prefixes = [str(Path(sys.base_prefix).resolve())]
    with tempfile.TemporaryDirectory(
        prefix=".research-agent-test-", dir=root.parent
    ) as temporary:
        isolated_root = Path(temporary) / "project"
        shutil.copytree(
            root,
            isolated_root,
            ignore=shutil.ignore_patterns(".git", ".test-home", ".test-tmp"),
        )
        project = json.dumps(str(isolated_root.resolve()))
        python_paths = " ".join(
            f"(subpath {json.dumps(path)})" for path in prefixes
        )
        profile = (
            "(version 1)\n"
            "(deny default)\n"
            "(allow process*)\n"
            "(allow file-read-data (literal \"/\"))\n"
            "(allow file-read-metadata (literal \"/\"))\n"
            "(allow file-read-metadata (subpath \"/Library\"))\n"
            f"(allow file-read* {python_paths} (subpath \"/System/Library\") "
            "(subpath \"/usr/lib\") "
            f"(subpath {project}))\n"
            f"(allow file-write* (subpath {project}) (literal \"/dev/null\"))\n"
            "(allow sysctl-read)\n"
        )
        env = {
            "PATH": os.path.dirname(sys.executable),
            "HOME": str(isolated_root / ".test-home"),
            "TMPDIR": str(isolated_root / ".test-tmp"),
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": f"{isolated_root}:{isolated_root / 'src'}",
        }
        (isolated_root / ".test-home").mkdir()
        (isolated_root / ".test-tmp").mkdir()
        command = [
            sandbox_exec,
            "-p",
            profile,
            str(interpreter),
            "-S",
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests",
        ]
        try:
            result = subprocess.run(
                command,
                cwd=isolated_root,
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (OSError, subprocess.SubprocessError):
            raise BuildError("Sandboxed test run failed to start or timed out.") from None
        if result.returncode:
            raise TestFailure(
                f"Sandboxed tests failed (exit code {result.returncode}); project was not pushed.",
                (result.stderr or result.stdout)[-3000:],
            )
        return ""


def build_project(idea: dict, *, model: str = "gpt-4.1-mini") -> dict[str, str | int]:
    name = idea.get("name")
    if not isinstance(name, str) or not _REPO.fullmatch(name):
        raise BuildError("The project slug is invalid.")
    base = Path.home() / "Documents" / "AI-Dev-Projects"
    base.mkdir(parents=True, exist_ok=True)
    base = base.resolve()
    root = base / name
    if root.exists():
        raise BuildError("Project checkout already exists; refusing to overwrite it.")
    try:
        _git(base, "rev-parse", "--show-toplevel")
    except BuildError:
        pass
    else:
        raise BuildError("Project workspace is inside a Git repository; refusing nested checkouts.")

    repository = obtain_repository(name, idea["description"])
    root.mkdir(mode=0o700)
    _git(root, "init", "--initial-branch=main")
    _git(root, "remote", "add", "origin", repository["clone_url"])

    contents: dict[str, str] = {}

    def commit_stage(stage: int, feedback: str = "", limit: int = 3000) -> str:
        """Generate, validate (with retries) and commit one change; returns error text."""
        error = feedback
        for _ in range(3):
            result = implementation_stage(
                idea, stage, _read_existing(root, limit), model=model, feedback=error
            )
            try:
                relative = _allowed_path(result["path"])
                key = relative.as_posix()
                local = {"src", relative.stem}
                if len(relative.parts) == 3:
                    local.add(relative.parts[1])
                for found in (root / "src").glob("*"):
                    local.add(found.stem)
                    for inner in found.glob("*.py") if found.is_dir() else ():
                        local.add(inner.stem)
                for found in (root / "tests").glob("*.py"):
                    local.add(found.stem)
                _validate_content(relative, result["content"], frozenset(local))
                if contents.get(key) == result["content"]:
                    raise BuildError("The change is identical to the existing file.")
                message = _clean_commit_message(result["commit_message"])
                if not _COMMIT.fullmatch(message):
                    raise BuildError("Generated commit message is invalid.")
            except BuildError as problem:
                error = str(problem)
                continue
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(result["content"], encoding="utf-8")
            contents[key] = result["content"]
            _git(root, "add", "--", key)
            _git(
                root,
                "commit",
                "-m",
                message,
            )
            return ""
        raise BuildError(f"Stage {stage + 1} failed after 3 attempts: {error}")

    for stage in range(10):
        commit_stage(stage)

    count = int(_git(root, "rev-list", "--count", "HEAD"))
    if count < 10:
        raise BuildError("Fewer than ten real implementation commits were created.")
    for attempt in range(7):
        try:
            _safe_test(root)
            break
        except TestFailure as failure:
            if attempt == 6:
                raise
            commit_stage(
                10,
                feedback=f"Tests failed (fix the source or the wrong test expectation):\n{failure.output}",
                limit=12000,
            )
            count += 1
    _git(root, "push", "--set-upstream", "origin", "main")
    return {
        "repository": repository["html_url"],
        "checkout": str(root),
        "commits": count,
    }
