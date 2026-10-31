import unittest
from unittest.mock import patch

from research_agent import github


class GitHubAPITests(unittest.TestCase):
    def test_authentication_returns_login_from_api(self):
        with patch.object(github, "_api", return_value=(200, {"login": "jonfvk"})):
            self.assertEqual(github.authenticated_login(), "jonfvk")

    def test_repository_is_created_public_and_empty(self):
        with patch.object(
            github,
            "_api",
            return_value=(
                201,
                {
                    "full_name": "jonfvk/demo",
                    "html_url": "https://github.com/jonfvk/demo",
                    "clone_url": "https://github.com/jonfvk/demo.git",
                },
            ),
        ) as api:
            result = github.create_public_repository("demo", "A test utility")

        self.assertEqual(result["full_name"], "jonfvk/demo")
        self.assertEqual(api.call_args.args[0], "/user/repos")
        self.assertEqual(api.call_args.kwargs["method"], "POST")
        self.assertEqual(
            api.call_args.kwargs["payload"],
            {
                "name": "demo",
                "description": "A test utility",
                "private": False,
                "auto_init": False,
            },
        )

    def test_invalid_repo_names_fail_before_api_request(self):
        for name in ("../escape", "", "contains spaces", "x" * 101):
            with self.subTest(name=name), patch.object(github, "_api") as api:
                with self.assertRaises(ValueError):
                    github.create_public_repository(name, "description")
                api.assert_not_called()


if __name__ == "__main__":
    unittest.main()
