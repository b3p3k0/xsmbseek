"""
SMBSeek Profile Manager Dialog

Provides profile save/load functionality using native OS file dialogs
with robust error handling, atomic file operations, and comprehensive validation.

Design Decision: Uses OS file dialogs instead of custom lists for simplicity
and native user experience. Implements atomic file operations to prevent
config corruption during profile operations.
"""

import os
import re
import json
import shutil
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import sys

# Add utils to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'utils'))

from style import get_theme


def atomic_write_json(file_path: str, data: Dict[str, Any]) -> None:
    """Write JSON atomically using temp file + os.replace to prevent corruption."""
    file_path = Path(file_path)

    # Write to temp file in same directory
    with tempfile.NamedTemporaryFile(
        mode='w',
        dir=file_path.parent,
        prefix=file_path.stem + '_tmp_',
        suffix='.json',
        delete=False
    ) as tmp_file:
        json.dump(data, tmp_file, indent=2)
        tmp_path = tmp_file.name

    # Atomic replace
    os.replace(tmp_path, file_path)


def resolve_config_path(config_path: Optional[str]) -> str:
    """Resolve config path with proper relative path handling."""
    if config_path:
        # Convert to absolute path against project root
        resolved_path = Path(config_path).resolve()
        if resolved_path.exists():
            return str(resolved_path)

        print(f"Warning: Specified config path {config_path} not found")

    # Try default path
    default_path = Path("smbseek/conf/config.json").resolve()
    if default_path.exists():
        return str(default_path)

    # Log warning and return best guess for better error messages
    print(f"Warning: Neither specified ({config_path}) nor default config found")
    return str(Path(config_path or "smbseek/conf/config.json").resolve())


def is_protected_file(target_path: str, config_path: str) -> bool:
    """Check if target would overwrite config or backup files."""
    target_resolved = Path(target_path).resolve()
    config_resolved = Path(config_path).resolve()
    backup_resolved = Path(f"{config_path}.xsmbseek").resolve()

    return target_resolved in [config_resolved, backup_resolved]


def sanitize_profile_path(path: str) -> str:
    """Sanitize and validate profile filename for filesystem safety."""
    directory = os.path.dirname(path)
    filename = os.path.basename(path)

    # Remove dangerous characters and collapse whitespace
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    filename = re.sub(r'\s+', ' ', filename).strip()

    # Validate non-empty result
    if not filename or filename == '.json':
        raise ValueError("Invalid filename: name cannot be empty")

    # Ensure .json extension
    if not filename.lower().endswith('.json'):
        filename += '.json'

    return os.path.join(directory, filename)


def ensure_backup(config_path: str) -> Dict[str, Any]:
    """Create backup with atomic operations to prevent corruption."""
    backup_path = f"{config_path}.xsmbseek"

    # Check if backup already exists
    if os.path.exists(backup_path):
        return {"success": True, "message": f"Using existing backup: {os.path.basename(backup_path)}"}

    # Check if original config exists
    if not os.path.exists(config_path):
        return {"success": True, "message": "No original config to back up"}

    try:
        # Read config data first
        with open(config_path, 'r') as f:
            config_data = json.load(f)

        # Write backup atomically
        atomic_write_json(backup_path, config_data)

        return {"success": True, "message": f"✅ Original config backed up as {os.path.basename(backup_path)}"}
    except (OSError, PermissionError) as e:
        return {"success": False, "message": f"⚠️ Backup creation failed: {e}"}
    except json.JSONDecodeError as e:
        return {"success": False, "message": f"⚠️ Invalid config file, backup skipped: {e}"}


def save_profile(parent: tk.Widget, config_path: str) -> Dict[str, Any]:
    """Save current config as profile with atomic file operations."""
    try:
        # Ensure .profiles directory exists
        profiles_dir = Path("./.profiles")
        profiles_dir.mkdir(exist_ok=True)
    except PermissionError:
        return {"success": False, "message": "Cannot create .profiles directory - read-only environment"}

    # Open save dialog
    profile_path = filedialog.asksaveasfilename(
        parent=parent,
        title="Save Profile As",
        initialdir=str(profiles_dir),
        defaultextension=".json",
        filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
    )

    if not profile_path:
        return {"success": True, "message": "Save cancelled"}

    try:
        # Sanitize and validate filename
        profile_path = sanitize_profile_path(profile_path)

        # Prevent overwriting protected files
        if is_protected_file(profile_path, config_path):
            return {"success": False, "message": "Cannot overwrite config or backup files"}

        # Read current config
        with open(config_path, 'r') as f:
            config_data = json.load(f)

        # Strip any existing metadata to prevent nesting
        if "_xsmbseek_profile" in config_data:
            del config_data["_xsmbseek_profile"]

        # Add fresh metadata
        config_data["_xsmbseek_profile"] = {
            "managed_by": "xsmbseek",
            "saved_at": datetime.now().isoformat() + "Z",
            "display_name": os.path.splitext(os.path.basename(profile_path))[0]
        }

        # Atomic write to prevent corruption
        atomic_write_json(profile_path, config_data)

        return {"success": True, "message": f"Profile saved as {os.path.basename(profile_path)}"}

    except ValueError as e:
        return {"success": False, "message": str(e)}
    except (PermissionError, OSError) as e:
        return {"success": False, "message": f"Save failed: {e}"}
    except json.JSONDecodeError as e:
        return {"success": False, "message": f"Invalid config file: {e}"}


def load_profile(parent: tk.Widget, config_path: str) -> Dict[str, Any]:
    """Load profile with atomic config file update."""
    profile_path = filedialog.askopenfilename(
        parent=parent,
        title="Load Profile",
        initialdir="./.profiles",
        filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
    )

    if not profile_path:
        return {"success": True, "message": "Load cancelled"}

    try:
        # Read and validate profile JSON
        with open(profile_path, 'r') as f:
            profile_data = json.load(f)

        # Validate it's a dictionary (basic sanity check)
        if not isinstance(profile_data, dict):
            return {"success": False, "message": "Invalid profile: not a configuration object"}

        # Strip metadata if present
        clean_config = profile_data.copy()
        if "_xsmbseek_profile" in clean_config:
            del clean_config["_xsmbseek_profile"]

        # Validate we have some expected config structure
        if not clean_config:
            return {"success": False, "message": "Invalid profile: no configuration data found"}

        # Atomic write to config file to prevent corruption
        try:
            atomic_write_json(config_path, clean_config)
        except PermissionError:
            return {"success": False, "message": "Cannot write to config file - read-only environment"}

        return {"success": True, "message": "Profile loaded. Next scans will use this configuration."}

    except json.JSONDecodeError as e:
        return {"success": False, "message": f"Invalid JSON file: {e}"}
    except (PermissionError, OSError) as e:
        return {"success": False, "message": f"Load failed: {e}"}


class ProfileManagerDialog:
    """
    Profile Manager Dialog with OS file dialogs and robust error handling.

    Provides save/load/edit functionality for SMBSeek configuration profiles
    using native file dialogs and atomic file operations to prevent corruption.
    """

    def __init__(self, parent: tk.Widget, config_path: Optional[str] = None):
        """
        Initialize profile manager dialog.

        Args:
            parent: Parent window
            config_path: Path to config file (None = auto-detect)
        """
        self.parent = parent
        self.config_path = resolve_config_path(config_path)
        self.theme = get_theme()
        self.readonly_mode = False

        # Dialog components
        self.dialog = None
        self.save_button = None
        self.load_button = None
        self.edit_button = None
        self.status_label = None

        # Test environment capabilities
        self._check_environment()

        # Create dialog
        self._create_dialog()

    def _check_environment(self) -> None:
        """Check environment capabilities with minimal file system impact."""
        try:
            # Test .profiles creation
            profiles_dir = Path("./.profiles")
            profiles_dir.mkdir(exist_ok=True)

            # Test config write access efficiently
            config_path = Path(self.config_path)
            if config_path.exists():
                # Quick append test instead of full rewrite
                with open(config_path, 'a') as f:
                    pass  # Just test we can open for append

        except (PermissionError, OSError):
            self.readonly_mode = True

    def _create_dialog(self) -> None:
        """Create the profile manager dialog."""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("Profile Manager")
        self.dialog.geometry("600x600")
        self.dialog.resizable(True, True)
        self.dialog.minsize(500, 350)

        # Apply theme
        self.theme.apply_to_widget(self.dialog, "main_window")

        # Make modal
        self.dialog.transient(self.parent)
        self.dialog.grab_set()

        # Create layout
        self._create_header()
        self._create_save_section()
        self._create_load_section()
        self._create_edit_section()
        self._create_status_section()
        self._create_button_frame()

        # Center dialog
        self._center_dialog()

    def _create_header(self) -> None:
        """Create dialog header with path information."""
        header_frame = tk.Frame(self.dialog)
        header_frame.pack(fill=tk.X, padx=20, pady=(20, 10))

        # Title
        title_label = self.theme.create_styled_label(
            header_frame,
            "🗂 Profile Manager",
            "title"
        )
        title_label.pack(anchor=tk.W)

        # Config path info
        config_info = f"Managed config: {self.config_path}"
        config_label = self.theme.create_styled_label(
            header_frame,
            config_info,
            "small"
        )
        config_label.pack(anchor=tk.W, pady=(5, 0))

        # Profiles directory info
        profiles_info = "Profiles stored in: ./.profiles/"
        profiles_label = self.theme.create_styled_label(
            header_frame,
            profiles_info,
            "small"
        )
        profiles_label.pack(anchor=tk.W, pady=(2, 0))

    def _create_save_section(self) -> None:
        """Create save profile section."""
        save_frame = tk.LabelFrame(self.dialog, text="Save Current Configuration")
        self.theme.apply_to_widget(save_frame, "card")
        save_frame.pack(fill=tk.X, padx=20, pady=(10, 5))

        # Description
        desc_label = self.theme.create_styled_label(
            save_frame,
            "Save the current configuration as a reusable profile",
            "body"
        )
        desc_label.pack(anchor=tk.W, padx=10, pady=(10, 5))

        # Save button
        self.save_button = tk.Button(
            save_frame,
            text="Save Profile As...",
            command=self._handle_save,
            state=tk.DISABLED if self.readonly_mode else tk.NORMAL
        )
        self.theme.apply_to_widget(self.save_button, "button_primary")
        self.save_button.pack(anchor=tk.W, padx=10, pady=(5, 10))

    def _create_load_section(self) -> None:
        """Create load profile section."""
        load_frame = tk.LabelFrame(self.dialog, text="Load Saved Configuration")
        self.theme.apply_to_widget(load_frame, "card")
        load_frame.pack(fill=tk.X, padx=20, pady=5)

        # Description
        desc_label = self.theme.create_styled_label(
            load_frame,
            "Load a previously saved profile to replace the current configuration",
            "body"
        )
        desc_label.pack(anchor=tk.W, padx=10, pady=(10, 5))

        # Load button
        self.load_button = tk.Button(
            load_frame,
            text="Load Profile...",
            command=self._handle_load,
            state=tk.DISABLED if self.readonly_mode else tk.NORMAL
        )
        self.theme.apply_to_widget(self.load_button, "button_secondary")
        self.load_button.pack(anchor=tk.W, padx=10, pady=(5, 10))

    def _create_edit_section(self) -> None:
        """Create edit configuration section."""
        edit_frame = tk.LabelFrame(self.dialog, text="Edit Current Configuration")
        self.theme.apply_to_widget(edit_frame, "card")
        edit_frame.pack(fill=tk.X, padx=20, pady=5)

        # Description
        desc_label = self.theme.create_styled_label(
            edit_frame,
            "Open the configuration editor to modify the current settings",
            "body"
        )
        desc_label.pack(anchor=tk.W, padx=10, pady=(10, 5))

        # Edit button
        self.edit_button = tk.Button(
            edit_frame,
            text="Open Config Editor",
            command=self._handle_edit
        )
        self.theme.apply_to_widget(self.edit_button, "button_secondary")
        self.edit_button.pack(anchor=tk.W, padx=10, pady=(5, 10))

    def _create_status_section(self) -> None:
        """Create status section with backup and environment info."""
        status_frame = tk.Frame(self.dialog)
        status_frame.pack(fill=tk.X, padx=20, pady=(10, 5))

        # Determine status message
        if self.readonly_mode:
            status_text = "❌ Read-only environment - profile operations disabled"
        else:
            backup_result = ensure_backup(self.config_path)
            status_text = backup_result["message"]

        self.status_label = self.theme.create_styled_label(
            status_frame,
            status_text,
            "small"
        )
        self.status_label.pack(anchor=tk.W)

    def _create_button_frame(self) -> None:
        """Create button frame with close button."""
        button_frame = tk.Frame(self.dialog)
        button_frame.pack(fill=tk.X, padx=20, pady=20)

        # Close button
        close_button = tk.Button(
            button_frame,
            text="Close",
            command=self._close_dialog
        )
        self.theme.apply_to_widget(close_button, "button_secondary")
        close_button.pack(side=tk.RIGHT)

    def _center_dialog(self) -> None:
        """Center dialog on parent."""
        self.dialog.update_idletasks()

        # Center on parent
        x = self.parent.winfo_x() + (self.parent.winfo_width() // 2) - (self.dialog.winfo_width() // 2)
        y = self.parent.winfo_y() + (self.parent.winfo_height() // 2) - (self.dialog.winfo_height() // 2)

        self.dialog.geometry(f"+{x}+{y}")

    def _handle_save(self) -> None:
        """Handle save profile button click."""
        result = save_profile(self.dialog, self.config_path)

        if result.get("success"):
            if "cancelled" not in result.get("message", "").lower():
                messagebox.showinfo("Save Profile", result["message"])
        else:
            messagebox.showerror("Save Profile", result.get("message", "Save failed"))

    def _handle_load(self) -> None:
        """Handle load profile button click."""
        result = load_profile(self.dialog, self.config_path)

        if result.get("success"):
            if "cancelled" not in result.get("message", "").lower():
                messagebox.showinfo("Load Profile", result["message"])
        else:
            messagebox.showerror("Load Profile", result.get("message", "Load failed"))

    def _handle_edit(self) -> None:
        """Handle edit config button click."""
        # Import here to avoid circular imports
        try:
            from config_editor_window import SimpleConfigEditorWindow
            editor = SimpleConfigEditorWindow(self.dialog, self.config_path)
            editor.show()
        except ImportError:
            messagebox.showwarning(
                "Config Editor",
                "Configuration editor not available. Please edit the config file manually."
            )

    def _close_dialog(self) -> None:
        """Close the dialog."""
        if self.dialog:
            self.dialog.destroy()

    def show_modal(self) -> Optional[Dict[str, Any]]:
        """
        Show dialog modally and return result.

        Returns:
            Result dict or None if cancelled
        """
        if self.dialog:
            self.dialog.wait_window()
        return None


def show_profile_manager(parent: tk.Widget, config_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Show profile manager dialog with robust error handling.

    Args:
        parent: Parent window
        config_path: Path to config file (None = auto-detect)

    Returns:
        dict: {"success": bool, "message": str} or None if cancelled
    """
    try:
        dialog = ProfileManagerDialog(parent, config_path)
        return dialog.show_modal()
    except Exception as e:
        return {"success": False, "message": f"Profile manager error: {e}"}