"""macOS Keychain storage for Research Agent credentials."""

import getpass
import subprocess
import sys
import warnings

SERVICE = "com.jonfvk.research-agent"
LEGACY_SERVICE = "com.codex-agentbuild.trend-project-builder"
GITHUB_ACCOUNT = "github-token"
OPENAI_ACCOUNT = "openai-api-key"
TAVILY_ACCOUNT = "tavily-api-key"
ACCOUNTS = {
    "github": GITHUB_ACCOUNT,
    "openai": OPENAI_ACCOUNT,
    "tavily": TAVILY_ACCOUNT,
}


class CredentialError(RuntimeError):
    """Credential storage or retrieval failed without exposing a value."""


def _backend():
    if sys.platform != "darwin":
        raise CredentialError("Research Agent requires macOS Keychain.")
    try:
        from keyring.backends.macOS import Keyring

        backend = Keyring()
        backend.keychain = None
        return backend
    except Exception:
        raise CredentialError("macOS Keychain is unavailable.") from None


def store(account: str, value: str) -> None:
    if account not in ACCOUNTS.values() or not value.strip():
        raise CredentialError("Invalid credential account or empty value.")
    try:
        _backend().set_password(SERVICE, account, value)
    except CredentialError:
        raise
    except Exception:
        raise CredentialError("Credential could not be stored in Keychain.") from None


def load(account: str) -> str:
    if account not in ACCOUNTS.values():
        raise CredentialError("Unknown credential account.")
    try:
        value = _backend().get_password(SERVICE, account)
    except CredentialError:
        raise
    except Exception:
        raise CredentialError("Credential could not be read from Keychain.") from None
    if not value:
        raise CredentialError(f"Credential is not configured: {account}.")
    return value


def status() -> dict[str, bool]:
    backend = _backend()
    try:
        return {
            label: bool(backend.get_password(SERVICE, account))
            for label, account in ACCOUNTS.items()
        }
    except Exception:
        raise CredentialError("Keychain credential status could not be read.") from None


def migrate_legacy_credentials(
    *, exclude_accounts: set[str] | None = None
) -> dict[str, bool]:
    """Copy the prior setup to this app's namespace and verify each value."""
    backend = _backend()
    excluded = exclude_accounts or set()
    migrated: dict[str, bool] = {}
    try:
        for label, account in ACCOUNTS.items():
            if account in excluded:
                migrated[label] = bool(backend.get_password(SERVICE, account))
                continue
            old = backend.get_password(LEGACY_SERVICE, account)
            if old is None:
                migrated[label] = bool(backend.get_password(SERVICE, account))
                continue
            current = backend.get_password(SERVICE, account)
            if current is not None and current != old:
                raise CredentialError(
                    f"Existing {label} credential differs; migration stopped without replacing it."
                )
            if current is None:
                backend.set_password(SERVICE, account, old)
            if backend.get_password(SERVICE, account) != old:
                raise CredentialError(f"{label} credential could not be verified after migration.")
            migrated[label] = True
    except CredentialError:
        raise
    except Exception:
        raise CredentialError("Credential migration failed; original entries were not deleted.") from None
    return migrated


def setup_tavily() -> None:
    _require_interactive_terminal()
    print("Enter a newly rotated Tavily key. Input is hidden.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            value = getpass.getpass("Tavily API key: ")
        store(TAVILY_ACCOUNT, value)
    except (KeyboardInterrupt, EOFError, getpass.GetPassWarning):
        raise CredentialError("Tavily credential setup cancelled.") from None


def _require_interactive_terminal() -> None:
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise CredentialError("Run credential setup directly in an interactive terminal.")


def setup(verify_github) -> str:
    _require_interactive_terminal()
    print("Credentials will be stored in macOS Keychain. Input is hidden.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            github = getpass.getpass("GitHub classic PAT (public_repo scope): ")
            login = verify_github(github)
            openai = getpass.getpass("OpenAI API key: ")
            tavily = getpass.getpass("Tavily API key: ")
        if not openai.strip() or not tavily.strip():
            raise CredentialError("OpenAI and Tavily credentials must not be empty.")
        store(GITHUB_ACCOUNT, github)
        store(OPENAI_ACCOUNT, openai)
        store(TAVILY_ACCOUNT, tavily)
        return login
    except (KeyboardInterrupt, EOFError, getpass.GetPassWarning):
        raise CredentialError("Credential setup cancelled; no values were displayed.") from None


def store_git_credential(login: str, token: str) -> None:
    """Store HTTPS Git auth using Apple's Keychain-backed credential helper."""
    try:
        exec_path = subprocess.run(
            ["git", "--exec-path"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        helper = f"{exec_path}/git-credential-osxkeychain"
        credential = (
            f"protocol=https\nhost=github.com\nusername={login}\n"
            f"password={token}\n\n"
        )
        subprocess.run(
            [helper, "store"],
            input=credential,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        raise CredentialError("Git credentials could not be stored in macOS Keychain.") from None
