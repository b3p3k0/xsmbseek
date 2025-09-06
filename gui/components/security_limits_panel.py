"""
Security Limits Configuration Panel

Provides GUI interface for configuring SMB security limits as per audit recommendations.
Includes validation, tooltips, and safe defaults to prevent misconfigurations.

Design Decision: Dedicated panel ensures security limits are prominently displayed
and easily adjustable while maintaining safe operational parameters.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import json
import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional, Callable

# Add utils to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'utils'))

from style import get_theme
from security_helpers import validate_smb_limits_config, get_default_smb_limits


class SecurityLimitsPanel:
    """
    Security limits configuration panel for SMB security settings.
    
    Implements audit requirement for configurable security limits with validation.
    Provides user-friendly interface for adjusting timeouts, size limits, and
    other security parameters while preventing dangerous configurations.
    """
    
    def __init__(self, parent: tk.Widget, config_path: str, 
                 on_config_changed: Optional[Callable] = None):
        """
        Initialize security limits panel.
        
        Args:
            parent: Parent widget to contain the panel
            config_path: Path to SMBSeek configuration file
            on_config_changed: Callback for configuration changes
        """
        self.parent = parent
        self.config_path = Path(config_path)
        self.on_config_changed = on_config_changed
        self.theme = get_theme()
        
        # Current configuration
        self.current_config = {}
        self.limits_config = {}
        
        # UI components
        self.panel_frame = None
        self.limit_vars = {}
        self.limit_entries = {}
        self.validation_labels = {}
        
        # Load current configuration
        self._load_configuration()
        
        # Create the panel
        self._create_panel()
        
        # Populate with current values
        self._populate_current_values()
    
    def _load_configuration(self) -> None:
        """Load current SMBSeek configuration."""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.current_config = json.load(f)
            else:
                self.current_config = {}
        except (json.JSONDecodeError, FileNotFoundError) as e:
            print(f"Warning: Could not load configuration: {e}")
            self.current_config = {}
        
        # Extract SMB limits or use defaults
        self.limits_config = self.current_config.get('limits', {}).get('smb', {})
        
        # Ensure we have all default values
        defaults = get_default_smb_limits()
        for key, default_value in defaults.items():
            if key not in self.limits_config:
                self.limits_config[key] = default_value
    
    def _create_panel(self) -> None:
        """Create the security limits configuration panel."""
        # Main panel frame
        self.panel_frame = tk.Frame(self.parent)
        self.theme.apply_to_widget(self.panel_frame, "card")
        self.panel_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Panel header
        self._create_panel_header()
        
        # Timeout settings section
        self._create_timeout_section()
        
        # Size limits section  
        self._create_size_limits_section()
        
        # Share limits section
        self._create_share_limits_section()
        
        # Security options section
        self._create_security_options_section()
        
        # Action buttons
        self._create_action_buttons()
    
    def _create_panel_header(self) -> None:
        """Create panel header with title and description."""
        header_frame = tk.Frame(self.panel_frame)
        self.theme.apply_to_widget(header_frame, "card")
        header_frame.pack(fill=tk.X, padx=15, pady=(15, 10))
        
        # Title
        title_label = self.theme.create_styled_label(
            header_frame,
            "🔒 Security Limits Configuration",
            "heading"
        )
        title_label.pack(anchor="w")
        
        # Description
        desc_text = ("Configure security limits and timeouts for SMB operations. "
                    "These settings help protect against malicious servers and network issues.")
        desc_label = self.theme.create_styled_label(
            header_frame,
            desc_text,
            "body",
            fg=self.theme.colors["text_secondary"],
            wraplength=600
        )
        desc_label.pack(anchor="w", pady=(5, 0))
    
    def _create_timeout_section(self) -> None:
        """Create timeout configuration section."""
        section_frame = self._create_section_frame("⏱️ Timeout Settings")
        
        # Timeout per stage
        self._create_limit_input(
            section_frame,
            'timeout_per_stage_seconds',
            'Timeout per Stage (seconds):',
            'Maximum time to wait for each scan stage to complete',
            1, 300
        )
        
        # Timeout per host
        self._create_limit_input(
            section_frame,
            'timeout_per_host_seconds',
            'Timeout per Host (seconds):',
            'Maximum time to spend testing each individual host',
            5, 3600
        )
    
    def _create_size_limits_section(self) -> None:
        """Create size limits configuration section."""
        section_frame = self._create_section_frame("📏 Size Limits")
        
        # Max PDU bytes
        self._create_limit_input(
            section_frame,
            'max_pdu_bytes',
            'Max PDU Size (bytes):',
            'Maximum size of SMB protocol data units (prevents oversized responses)',
            1024, 1048576
        )
        
        # Max stdout bytes
        self._create_limit_input(
            section_frame,
            'max_stdout_bytes',
            'Max Output Size (bytes):',
            'Maximum size of command output (prevents memory exhaustion)',
            1024, 104857600
        )
    
    def _create_share_limits_section(self) -> None:
        """Create share limits configuration section."""
        section_frame = self._create_section_frame("📂 Share Limits")
        
        # Max shares
        self._create_limit_input(
            section_frame,
            'max_shares',
            'Max Shares per Host:',
            'Maximum number of shares to enumerate per server',
            1, 10000
        )
        
        # Max share name length
        self._create_limit_input(
            section_frame,
            'max_share_name_len',
            'Max Share Name Length:',
            'Maximum length of share names (prevents buffer overflows)',
            1, 255
        )
    
    def _create_security_options_section(self) -> None:
        """Create security options configuration section."""
        section_frame = self._create_section_frame("🛡️ Security Options")
        
        # Signing required
        self._create_boolean_option(
            section_frame,
            'signing_required',
            'Require SMB Signing:',
            'Enforce message signing to prevent man-in-the-middle attacks'
        )
        
        # Resolve NetBIOS
        self._create_boolean_option(
            section_frame,
            'resolve_netbios',
            'Resolve NetBIOS Names:',
            'Enable NetBIOS name resolution (may expose additional information)'
        )
    
    def _create_section_frame(self, title: str) -> tk.Frame:
        """
        Create a section frame with title.
        
        Args:
            title: Section title
            
        Returns:
            Section frame widget
        """
        section_frame = tk.Frame(self.panel_frame)
        self.theme.apply_to_widget(section_frame, "card")
        section_frame.pack(fill=tk.X, padx=15, pady=(5, 10))
        
        # Section title
        title_label = self.theme.create_styled_label(
            section_frame,
            title,
            "subheading"
        )
        title_label.pack(anchor="w", padx=10, pady=(10, 5))
        
        return section_frame
    
    def _create_limit_input(self, parent: tk.Widget, key: str, label: str, 
                           tooltip: str, min_val: int, max_val: int) -> None:
        """
        Create a numeric input field for a security limit.
        
        Args:
            parent: Parent widget
            key: Configuration key
            label: Display label
            tooltip: Help text
            min_val: Minimum allowed value
            max_val: Maximum allowed value
        """
        input_frame = tk.Frame(parent)
        self.theme.apply_to_widget(input_frame, "card")
        input_frame.pack(fill=tk.X, padx=10, pady=(0, 8))
        
        # Label with tooltip
        label_frame = tk.Frame(input_frame)
        self.theme.apply_to_widget(label_frame, "card")
        label_frame.pack(fill=tk.X)
        
        main_label = self.theme.create_styled_label(
            label_frame,
            label,
            "body"
        )
        main_label.pack(side=tk.LEFT)
        
        # Tooltip/help text
        help_label = self.theme.create_styled_label(
            label_frame,
            f"  ℹ️ {tooltip}",
            "small",
            fg=self.theme.colors["text_secondary"]
        )
        help_label.pack(side=tk.LEFT)
        
        # Input frame with validation
        entry_frame = tk.Frame(input_frame)
        self.theme.apply_to_widget(entry_frame, "card")
        entry_frame.pack(fill=tk.X, pady=(5, 0))
        
        # Create StringVar for validation
        var = tk.StringVar()
        self.limit_vars[key] = var
        
        # Entry field
        entry = tk.Entry(
            entry_frame,
            textvariable=var,
            width=15,
            font=self.theme.fonts["body"]
        )
        entry.pack(side=tk.LEFT)
        
        self.limit_entries[key] = entry
        
        # Valid range label
        range_label = self.theme.create_styled_label(
            entry_frame,
            f"  (range: {min_val:,} - {max_val:,})",
            "small",
            fg=self.theme.colors["text_secondary"]
        )
        range_label.pack(side=tk.LEFT)
        
        # Validation feedback label
        validation_label = self.theme.create_styled_label(
            entry_frame,
            "",
            "small"
        )
        validation_label.pack(side=tk.LEFT, padx=(10, 0))
        self.validation_labels[key] = validation_label
        
        # Bind validation
        var.trace_add("write", lambda *args, k=key: self._validate_field(k, min_val, max_val))
    
    def _create_boolean_option(self, parent: tk.Widget, key: str, 
                              label: str, tooltip: str) -> None:
        """
        Create a boolean checkbox option.
        
        Args:
            parent: Parent widget
            key: Configuration key
            label: Display label
            tooltip: Help text
        """
        option_frame = tk.Frame(parent)
        self.theme.apply_to_widget(option_frame, "card")
        option_frame.pack(fill=tk.X, padx=10, pady=(0, 8))
        
        # Create BooleanVar
        var = tk.BooleanVar()
        self.limit_vars[key] = var
        
        # Checkbox with label
        checkbox = tk.Checkbutton(
            option_frame,
            variable=var,
            text=label,
            font=self.theme.fonts["body"]
        )
        self.theme.apply_to_widget(checkbox, "card")
        checkbox.pack(side=tk.LEFT)
        
        # Tooltip
        help_label = self.theme.create_styled_label(
            option_frame,
            f"  ℹ️ {tooltip}",
            "small",
            fg=self.theme.colors["text_secondary"]
        )
        help_label.pack(side=tk.LEFT)
    
    def _validate_field(self, key: str, min_val: int, max_val: int) -> None:
        """
        Validate a numeric field in real-time.
        
        Args:
            key: Configuration key being validated
            min_val: Minimum allowed value
            max_val: Maximum allowed value
        """
        validation_label = self.validation_labels[key]
        value_str = self.limit_vars[key].get().strip()
        
        if not value_str:
            validation_label.config(text="", fg=self.theme.colors["text_secondary"])
            return
        
        try:
            value = int(value_str)
            if value < min_val:
                validation_label.config(text=f"⚠️ Too low (min: {min_val:,})", fg='#dc3545')
            elif value > max_val:
                validation_label.config(text=f"⚠️ Too high (max: {max_val:,})", fg='#dc3545')
            else:
                validation_label.config(text="✓ Valid", fg='#28a745')
        except ValueError:
            validation_label.config(text="⚠️ Must be a number", fg='#dc3545')
    
    def _populate_current_values(self) -> None:
        """Populate input fields with current configuration values."""
        for key, var in self.limit_vars.items():
            if key in self.limits_config:
                value = self.limits_config[key]
                if isinstance(var, tk.BooleanVar):
                    var.set(bool(value))
                else:
                    var.set(str(value))
    
    def _create_action_buttons(self) -> None:
        """Create action buttons for save/reset operations."""
        button_frame = tk.Frame(self.panel_frame)
        self.theme.apply_to_widget(button_frame, "card")
        button_frame.pack(fill=tk.X, padx=15, pady=(5, 15))
        
        # Reset to defaults button (left)
        reset_button = tk.Button(
            button_frame,
            text="🔄 Reset to Defaults",
            command=self._reset_to_defaults
        )
        self.theme.apply_to_widget(reset_button, "button_secondary")
        reset_button.pack(side=tk.LEFT)
        
        # Save configuration button (right)
        save_button = tk.Button(
            button_frame,
            text="💾 Save Configuration",
            command=self._save_configuration
        )
        self.theme.apply_to_widget(save_button, "button_primary")
        save_button.pack(side=tk.RIGHT)
        
        # Validate button (center)
        validate_button = tk.Button(
            button_frame,
            text="✓ Validate Settings",
            command=self._validate_all_settings
        )
        self.theme.apply_to_widget(validate_button, "button_secondary")
        validate_button.pack(side=tk.RIGHT, padx=(0, 10))
    
    def _reset_to_defaults(self) -> None:
        """Reset all settings to secure defaults."""
        result = messagebox.askyesno(
            "Reset to Defaults",
            "Reset all security limits to secure defaults?\n\n"
            "This will overwrite your current settings."
        )
        
        if result:
            defaults = get_default_smb_limits()
            for key, var in self.limit_vars.items():
                if key in defaults:
                    value = defaults[key]
                    if isinstance(var, tk.BooleanVar):
                        var.set(bool(value))
                    else:
                        var.set(str(value))
    
    def _validate_all_settings(self) -> None:
        """Validate all current settings and show results."""
        # Collect current values
        current_values = {}
        for key, var in self.limit_vars.items():
            if isinstance(var, tk.BooleanVar):
                current_values[key] = var.get()
            else:
                try:
                    current_values[key] = int(var.get())
                except ValueError:
                    current_values[key] = var.get()  # Keep as string for error reporting
        
        # Validate using security helpers
        errors = validate_smb_limits_config(current_values)
        
        if not errors:
            messagebox.showinfo(
                "Validation Successful",
                "✅ All security limits are valid and within safe ranges."
            )
        else:
            error_msg = "Validation errors found:\n\n"
            for field, error in errors.items():
                error_msg += f"• {field}: {error}\n"
            
            messagebox.showerror(
                "Validation Errors",
                error_msg + "\nPlease correct these issues before saving."
            )
    
    def _save_configuration(self) -> None:
        """Save the current security limits to configuration file."""
        # First validate all settings
        current_values = {}
        for key, var in self.limit_vars.items():
            if isinstance(var, tk.BooleanVar):
                current_values[key] = var.get()
            else:
                try:
                    current_values[key] = int(var.get())
                except ValueError:
                    messagebox.showerror(
                        "Invalid Value",
                        f"Invalid numeric value for {key}: '{var.get()}'\n\n"
                        "Please enter a valid number."
                    )
                    return
        
        # Validate using security helpers
        errors = validate_smb_limits_config(current_values)
        if errors:
            error_msg = "Cannot save configuration due to validation errors:\n\n"
            for field, error in errors.items():
                error_msg += f"• {field}: {error}\n"
            
            messagebox.showerror("Save Failed", error_msg)
            return
        
        try:
            # Update configuration structure
            if 'limits' not in self.current_config:
                self.current_config['limits'] = {}
            if 'smb' not in self.current_config['limits']:
                self.current_config['limits']['smb'] = {}
            
            # Update SMB limits
            self.current_config['limits']['smb'].update(current_values)
            
            # Save to file
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.current_config, f, indent=2)
            
            messagebox.showinfo(
                "Configuration Saved",
                f"Security limits have been saved to:\n{self.config_path}\n\n"
                "The new settings will take effect for future scans."
            )
            
            # Notify parent of configuration change
            if self.on_config_changed:
                self.on_config_changed()
                
        except Exception as e:
            messagebox.showerror(
                "Save Error",
                f"Failed to save configuration:\n{str(e)}\n\n"
                "Please check file permissions and try again."
            )
    
    def get_current_limits(self) -> Dict[str, Any]:
        """
        Get current limit values from the UI.
        
        Returns:
            Dictionary of current limit values
        """
        current_values = {}
        for key, var in self.limit_vars.items():
            if isinstance(var, tk.BooleanVar):
                current_values[key] = var.get()
            else:
                try:
                    current_values[key] = int(var.get())
                except ValueError:
                    current_values[key] = None  # Invalid value
        
        return current_values


def create_security_limits_panel(parent: tk.Widget, config_path: str,
                                on_config_changed: Optional[Callable] = None) -> SecurityLimitsPanel:
    """
    Create a security limits configuration panel.
    
    Args:
        parent: Parent widget
        config_path: Path to SMBSeek configuration file
        on_config_changed: Callback for configuration changes
        
    Returns:
        SecurityLimitsPanel instance
    """
    return SecurityLimitsPanel(parent, config_path, on_config_changed)


# Test function for development
def test_security_limits_panel():
    """Test the security limits panel."""
    root = tk.Tk()
    root.geometry("800x600")
    root.title("Security Limits Panel Test")
    
    # Create test configuration path
    test_config_path = "test_config.json"
    
    panel = create_security_limits_panel(root, test_config_path)
    
    root.mainloop()


if __name__ == "__main__":
    test_security_limits_panel()