"""
Utilities for validating and selecting SMBSeek database paths at startup.

This module centralizes the logic that ensures a usable database exists
before the GUI fully launches. It can fall back to the database setup dialog
and shows informative error messages when validation fails.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional, Any

try:
    import tkinter as tk
    from tkinter import messagebox as tk_messagebox
except Exception:  # pragma: no cover - tkinter may be unavailable in tests
    tk = None
    tk_messagebox = None

from database_access import DatabaseReader

try:
    from database_setup_dialog import show_database_setup_dialog
except ImportError:  # pragma: no cover - dialog not available in some contexts
    show_database_setup_dialog = None  # type: ignore


DialogFactory = Callable[..., Optional[str]]
MessageboxModule = Any
DatabaseReaderFactory = Callable[..., DatabaseReader]


class _TkRootContext:
    """Create a temporary hidden Tk root when needed for dialogs/messageboxes."""

    def __init__(self, parent: Optional[Any]):
        self.parent = parent
        self._created_root = None

    def __enter__(self) -> Optional[Any]:
        if self.parent or tk is None:
            return self.parent

        # Reuse default root if it already exists
        default_root = getattr(tk, "_default_root", None)
        if default_root:
            return default_root

        try:
            self._created_root = tk.Tk()
            self._created_root.withdraw()
            return self._created_root
        except Exception:
            # If Tk cannot be initialized (headless tests), skip creating a root.
            self._created_root = None
            return None

    def __exit__(self, exc_type, exc_value, exc_traceback) -> None:
        if self._created_root:
            try:
                self._created_root.destroy()
            except Exception:
                pass


def ensure_database_available(
    initial_db_path: Optional[str],
    config_path: Optional[str] = None,
    parent: Optional[Any] = None,
    dialog_factory: Optional[DialogFactory] = None,
    messagebox_module: Optional[MessageboxModule] = None,
    db_reader_factory: Optional[DatabaseReaderFactory] = None,
) -> Optional[str]:
    """
    Validate that a usable SMBSeek database exists, showing the setup dialog if needed.

    Args:
        initial_db_path: Path that should be validated first.
        config_path: SMBSeek configuration path displayed in the dialog.
        parent: Optional Tk parent window.
        dialog_factory: Optional override for the database setup dialog.
        messagebox_module: Optional override for tkinter.messagebox (for testing).
        db_reader_factory: Optional factory to create DatabaseReader-like objects.

    Returns:
        Validated database path, or None if the user chose to exit.
    """
    dialog_factory = dialog_factory or show_database_setup_dialog
    messagebox_module = messagebox_module or tk_messagebox
    db_reader_cls = db_reader_factory or DatabaseReader
    config_path = config_path or "./smbseek/conf/config.json"

    temp_db_reader = db_reader_cls()
    current_path = initial_db_path

    if current_path:
        validation_result = temp_db_reader.validate_database(current_path)
        if validation_result.get("valid"):
            return current_path

    with _TkRootContext(parent) as active_parent:
        while True:
            if not dialog_factory:
                # No dialog available; stop to avoid infinite loop.
                return None

            selected_db_path = dialog_factory(
                parent=active_parent,
                initial_db_path=current_path,
                config_path=config_path,
            )

            if selected_db_path is None:
                # User chose to exit.
                return None

            validation_result = temp_db_reader.validate_database(selected_db_path)
            if validation_result.get("valid"):
                return selected_db_path

            error_text = validation_result.get("error") or "Unknown validation error"
            message = (
                "Selected database is not valid:\n"
                f"{error_text}\n\n"
                "Please try a different option."
            )

            if messagebox_module:
                try:
                    messagebox_module.showerror(
                        "Database Validation Failed",
                        message,
                        parent=active_parent,
                    )
                except Exception:
                    # Fall back to console logging if messagebox fails.
                    print(f"Database Validation Failed: {message}")
            else:  # pragma: no cover - fallback for non-GUI environments
                print(f"Database Validation Failed: {message}")

            current_path = selected_db_path
