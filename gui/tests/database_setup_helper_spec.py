"""
Tests for the database setup helper utilities.
"""

import unittest
import sys
from pathlib import Path

# Ensure utils are importable when running tests directly
gui_dir = Path(__file__).parent.parent
sys.path.insert(0, str(gui_dir / "utils"))

from database_setup_helper import ensure_database_available


class DummyReader:
    """Simple stand-in for DatabaseReader with configurable responses."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def validate_database(self, path):
        self.calls.append(path)
        return self.responses.get(path, {"valid": False, "error": "missing"})


class DummyMessagebox:
    """Capture messagebox interactions without requiring tkinter."""

    def __init__(self):
        self.errors = []

    def showerror(self, title, message, parent=None):
        self.errors.append((title, message, parent))


class TestDatabaseSetupHelper(unittest.TestCase):
    """Unit tests for ensure_database_available."""

    def test_returns_initial_valid_path(self):
        """Helper should accept the first path if validation passes."""
        responses = {"valid.db": {"valid": True}}
        result = ensure_database_available(
            initial_db_path="valid.db",
            parent=object(),
            dialog_factory=lambda **kwargs: self.fail("Dialog should not be invoked"),
            messagebox_module=DummyMessagebox(),
            db_reader_factory=lambda: DummyReader(responses),
        )
        self.assertEqual(result, "valid.db")

    def test_prompts_until_valid_path_selected(self):
        """Helper should keep prompting until a valid path is chosen."""
        responses = {
            "missing.db": {"valid": False, "error": "not found"},
            "bad.db": {"valid": False, "error": "schema mismatch"},
            "good.db": {"valid": True},
        }
        messagebox = DummyMessagebox()
        selections = iter(["bad.db", "good.db"])

        def dialog_factory(**kwargs):
            return next(selections, None)

        result = ensure_database_available(
            initial_db_path="missing.db",
            parent=object(),
            dialog_factory=dialog_factory,
            messagebox_module=messagebox,
            db_reader_factory=lambda: DummyReader(responses),
        )

        self.assertEqual(result, "good.db")
        self.assertEqual(len(messagebox.errors), 1)
        self.assertIn("schema mismatch", messagebox.errors[0][1])

    def test_returns_none_when_user_cancels(self):
        """Helper should return None if the dialog callback returns None."""
        responses = {"missing.db": {"valid": False, "error": "missing"}}
        result = ensure_database_available(
            initial_db_path="missing.db",
            parent=object(),
            dialog_factory=lambda **kwargs: None,
            messagebox_module=DummyMessagebox(),
            db_reader_factory=lambda: DummyReader(responses),
        )
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
