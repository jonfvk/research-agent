import unittest
from unittest.mock import Mock, patch

from research_agent import credentials


class CredentialTests(unittest.TestCase):
    def test_store_requires_known_account_and_nonempty_value(self):
        with patch.object(credentials, "_backend") as backend:
            with self.assertRaises(credentials.CredentialError):
                credentials.store("unknown", "value")
            with self.assertRaises(credentials.CredentialError):
                credentials.store(credentials.GITHUB_ACCOUNT, "  ")
            backend.assert_not_called()

    def test_migration_copies_and_verifies_without_deleting_source(self):
        backend = Mock()
        old_values = {
            (credentials.LEGACY_SERVICE, account): f"fake-{label}"
            for label, account in credentials.ACCOUNTS.items()
        }

        def get_password(service, account):
            return old_values.get((service, account))

        backend.get_password.side_effect = get_password

        def set_password(service, account, value):
            old_values[service, account] = value

        backend.set_password.side_effect = set_password
        with patch.object(credentials, "_backend", return_value=backend):
            self.assertEqual(
                credentials.migrate_legacy_credentials(),
                {"github": True, "openai": True, "tavily": True},
            )
        self.assertEqual(backend.set_password.call_count, 3)
        backend.delete_password.assert_not_called()

    def test_migration_refuses_conflicts_without_overwrite(self):
        backend = Mock()
        backend.get_password.side_effect = lambda service, account: (
            "legacy" if service == credentials.LEGACY_SERVICE
            else "different" if service == credentials.SERVICE
            else None
        )
        with patch.object(credentials, "_backend", return_value=backend):
            with self.assertRaises(credentials.CredentialError):
                credentials.migrate_legacy_credentials()
        backend.set_password.assert_not_called()

    def test_migration_can_skip_tavily_rotation(self):
        backend = Mock()
        values = {
            (credentials.LEGACY_SERVICE, account): f"legacy-{label}"
            for label, account in credentials.ACCOUNTS.items()
        }
        backend.get_password.side_effect = lambda service, account: values.get(
            (service, account)
        )
        backend.set_password.side_effect = (
            lambda service, account, value: values.__setitem__(
                (service, account), value
            )
        )
        with patch.object(credentials, "_backend", return_value=backend):
            result = credentials.migrate_legacy_credentials(
                exclude_accounts={credentials.TAVILY_ACCOUNT}
            )

        self.assertEqual(result, {"github": True, "openai": True, "tavily": False})
        self.assertEqual(backend.set_password.call_count, 2)
        self.assertNotIn(
            (credentials.SERVICE, credentials.TAVILY_ACCOUNT),
            values,
        )

    def test_setup_tavily_prompts_without_echo(self):
        with (
            patch.object(credentials.sys.stdin, "isatty", return_value=True),
            patch.object(credentials.sys.stderr, "isatty", return_value=True),
            patch.object(credentials.getpass, "getpass", return_value="rotated-tavily-key"),
            patch.object(credentials, "store") as store,
        ):
            credentials.setup_tavily()
        store.assert_called_once_with(credentials.TAVILY_ACCOUNT, "rotated-tavily-key")


if __name__ == "__main__":
    unittest.main()
