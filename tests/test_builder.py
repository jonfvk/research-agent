import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from research_agent.builder import BuildError, _allowed_path, _safe_test, _validate_content


class BuilderSafetyTests(unittest.TestCase):
    @unittest.skipUnless(
        sys.platform == "darwin" and shutil.which("sandbox-exec"),
        "requires macOS sandbox-exec",
    )
    def test_sandbox_runs_tests_without_exposing_checkout_for_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            tests = root / "tests"
            tests.mkdir(parents=True)
            outside = root / "outside.txt"
            test_source = (
                "import unittest\nfrom pathlib import Path\n"
                "class SandboxTest(unittest.TestCase):\n"
                "    def test_cannot_write_checkout(self):\n"
                f"        with self.assertRaises(PermissionError): Path({str(outside)!r}).write_text('escape')\n"
            )
            (tests / "test_sandbox.py").write_text(test_source, encoding="utf-8")

            _safe_test(root)

            self.assertFalse(outside.exists())

    def test_allowed_project_paths(self):
        for value in (
            "README.md",
            "pyproject.toml",
            ".gitignore",
            "src/report_tool/core.py",
            "tests/test_core.py",
            "docs/design.md",
        ):
            with self.subTest(path=value):
                self.assertEqual(_allowed_path(value), Path(value))

    def test_rejects_path_traversal_and_executable_artifacts(self):
        for value in (
            "../escape.py",
            "src/../../escape.py",
            "/tmp/escape.py",
            "scripts/install.sh",
            ".github/workflows/publish.yml",
            "src/tool.py/extra.py",
        ):
            with self.subTest(path=value), self.assertRaises(BuildError):
                _allowed_path(value)

    def test_rejects_dangerous_code_patterns(self):
        for content in (
            "import subprocess\n",
            "import socket\n",
            "eval('1 + 1')\n",
            "import keyring\n",
        ):
            with self.subTest(content=content), self.assertRaises(BuildError):
                _validate_content(Path("src/tool/core.py"), content)

    def test_rejects_python_syntax_error_and_oversize(self):
        with self.assertRaisesRegex(BuildError, "syntax"):
            _validate_content(Path("src/tool/core.py"), "def broken(:\n")
        with self.assertRaisesRegex(BuildError, "size"):
            _validate_content(Path("README.md"), "x" * 80_001)


if __name__ == "__main__":
    unittest.main()
