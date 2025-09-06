"""
SMBSeek Scan Dialog

Modal dialog for configuring and starting new SMB security scans.
Provides simple interface for country selection and configuration management.

Design Decision: Simple modal approach focuses on essential parameters
while directing users to configuration editor for advanced settings.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import os
import sys
from pathlib import Path
from typing import Optional, Callable, Dict, Any

# Add utils to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'utils'))

from style import get_theme
from smb1_warning_dialog import show_smb1_warning_dialog


class ScanDialog:
    """
    Modal dialog for configuring and starting SMB scans with security controls.
    
    Implements audit security requirements:
    - SMB1 toggle with explicit warning and consent
    - Credential controls (disabled for SMB1 mode)
    - Security policy banner showing current mode
    - Safe-by-default SMB2/3 scanning
    
    Design Pattern: Enhanced security-focused modal with comprehensive
    controls for both safe default and legacy discovery modes.
    """
    
    def __init__(self, parent: tk.Widget, config_path: str, 
                 config_editor_callback: Callable[[str], None],
                 scan_start_callback: Callable[[Dict[str, Any]], None]):
        """
        Initialize enhanced scan dialog with security controls.
        
        Args:
            parent: Parent widget
            config_path: Path to configuration file
            config_editor_callback: Function to open config editor
            scan_start_callback: Function to start scan with parameters dict
        """
        self.parent = parent
        self.config_path = Path(config_path).resolve()
        self.config_editor_callback = config_editor_callback
        self.scan_start_callback = scan_start_callback
        self.theme = get_theme()
        
        # Dialog result
        self.result = None
        self.scan_params = None
        
        # Security state
        self.smb1_enabled = False
        self.smb1_consent_given = False
        
        # UI components
        self.dialog = None
        self.country_var = tk.StringVar()
        self.country_entry = None
        
        # Security control variables
        self.smb1_var = tk.BooleanVar()
        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()
        
        # Security control widgets
        self.smb1_checkbox = None
        self.username_entry = None
        self.password_entry = None
        self.policy_banner = None
        self.credential_frame = None
        
        self._create_dialog()
    
    def _create_dialog(self) -> None:
        """Create the enhanced scan configuration dialog with security controls."""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("Start New Scan")
        self.dialog.geometry("600x700")
        self.dialog.minsize(500, 600)
        
        # Apply theme
        self.theme.apply_to_widget(self.dialog, "main_window")
        
        # Make modal
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        
        # Center dialog
        self._center_dialog()
        
        # Build UI
        self._create_header()
        self._create_security_policy_banner()
        self._create_scan_options()
        self._create_security_options()
        self._create_credential_controls()
        self._create_config_section()
        self._create_button_panel()
        
        # Setup event handlers
        self._setup_event_handlers()
        
        # Initialize security state
        self._update_security_controls()
        
        # Focus on country field
        self._focus_country_field()
    
    def _center_dialog(self) -> None:
        """Center dialog on parent window."""
        self.dialog.update_idletasks()
        
        # Get parent position and size
        parent_x = self.parent.winfo_x()
        parent_y = self.parent.winfo_y()
        parent_width = self.parent.winfo_width()
        parent_height = self.parent.winfo_height()
        
        # Calculate center position
        width = self.dialog.winfo_width()
        height = self.dialog.winfo_height()
        x = parent_x + (parent_width // 2) - (width // 2)
        y = parent_y + (parent_height // 2) - (height // 2)
        
        self.dialog.geometry(f"{width}x{height}+{x}+{y}")
    
    def _create_header(self) -> None:
        """Create dialog header with title and description."""
        header_frame = tk.Frame(self.dialog)
        self.theme.apply_to_widget(header_frame, "main_window")
        header_frame.pack(fill=tk.X, padx=20, pady=(15, 5))
        
        # Title
        title_label = self.theme.create_styled_label(
            header_frame,
            "🔍 Start New Security Scan",
            "heading"
        )
        title_label.pack(anchor="w")
        
        # Description
        desc_label = self.theme.create_styled_label(
            header_frame,
            "Configure and start a new SMB security scan to discover accessible shares.",
            "body",
            fg=self.theme.colors["text_secondary"]
        )
        desc_label.pack(anchor="w", pady=(5, 0))
    
    def _create_security_policy_banner(self) -> None:
        """Create security policy banner showing current scan mode."""
        banner_frame = tk.Frame(self.dialog)
        banner_frame.configure(bg='#e8f5e8', relief='solid', borderwidth=1)  # Light green for safe mode
        banner_frame.pack(fill=tk.X, padx=20, pady=(0, 5))
        
        # Policy banner label
        self.policy_banner = tk.Label(
            banner_frame,
            text="🔒 Security Policy: SMB2/SMB3 only • Signing required • Safe by default",
            font=self.theme.fonts["body"],
            fg='#155724',  # Dark green text
            bg='#e8f5e8',
            padx=10,
            pady=8
        )
        self.policy_banner.pack(fill=tk.X)
    
    def _create_scan_options(self) -> None:
        """Create scan configuration options."""
        options_frame = tk.Frame(self.dialog)
        self.theme.apply_to_widget(options_frame, "card")
        options_frame.pack(fill=tk.X, padx=20, pady=5)
        
        # Section title
        section_title = self.theme.create_styled_label(
            options_frame,
            "Scan Parameters",
            "heading"
        )
        section_title.pack(anchor="w", padx=15, pady=(10, 5))
        
        # Country selection
        country_container = tk.Frame(options_frame)
        self.theme.apply_to_widget(country_container, "card")
        country_container.pack(fill=tk.X, padx=15, pady=(0, 10))
        
        # Country label and input
        country_label = self.theme.create_styled_label(
            country_container,
            "Country Code (optional):",
            "body"
        )
        country_label.pack(anchor="w")
        
        # Country input with example
        country_input_frame = tk.Frame(country_container)
        self.theme.apply_to_widget(country_input_frame, "card")
        country_input_frame.pack(fill=tk.X, pady=(5, 0))
        
        self.country_entry = tk.Entry(
            country_input_frame,
            textvariable=self.country_var,
            width=10,
            font=self.theme.fonts["body"]
        )
        self.country_entry.pack(side=tk.LEFT)
        
        example_label = self.theme.create_styled_label(
            country_input_frame,
            "  (e.g., US, GB, CA or US,GB,CA - leave blank for global scan)",
            "small",
            fg=self.theme.colors["text_secondary"]
        )
        example_label.pack(side=tk.LEFT)
    
    def _create_security_options(self) -> None:
        """Create security options including SMB1 toggle."""
        security_frame = tk.Frame(self.dialog)
        self.theme.apply_to_widget(security_frame, "card")
        security_frame.pack(fill=tk.X, padx=20, pady=5)
        
        # Section title
        section_title = self.theme.create_styled_label(
            security_frame,
            "Security Options",
            "heading"
        )
        section_title.pack(anchor="w", padx=15, pady=(10, 5))
        
        # SMB1 toggle with warning
        smb1_container = tk.Frame(security_frame)
        self.theme.apply_to_widget(smb1_container, "card")
        smb1_container.pack(fill=tk.X, padx=15, pady=(0, 10))
        
        self.smb1_checkbox = tk.Checkbutton(
            smb1_container,
            variable=self.smb1_var,
            text="⚠️ Enable SMB1 discovery (one run only)",
            font=self.theme.fonts["body"],
            command=self._on_smb1_toggle
        )
        self.smb1_checkbox.pack(anchor="w")
        
        # Warning text for SMB1
        warning_label = self.theme.create_styled_label(
            smb1_container,
            "SMB1 is a legacy protocol with security risks. Use only when required for legacy systems.",
            "small",
            fg='#dc3545',  # Red warning text
            wraplength=500
        )
        warning_label.pack(anchor="w", padx=20, pady=(2, 0))
    
    def _create_credential_controls(self) -> None:
        """Create credential input controls."""
        self.credential_frame = tk.Frame(self.dialog)
        self.theme.apply_to_widget(self.credential_frame, "card")
        self.credential_frame.pack(fill=tk.X, padx=20, pady=5)
        
        # Section title
        cred_title = self.theme.create_styled_label(
            self.credential_frame,
            "Authentication (Optional)",
            "heading"
        )
        cred_title.pack(anchor="w", padx=15, pady=(10, 5))
        
        # Username input
        username_container = tk.Frame(self.credential_frame)
        self.theme.apply_to_widget(username_container, "card")
        username_container.pack(fill=tk.X, padx=15, pady=(0, 5))
        
        username_label = self.theme.create_styled_label(
            username_container,
            "Username (leave blank for anonymous):",
            "body"
        )
        username_label.pack(anchor="w")
        
        self.username_entry = tk.Entry(
            username_container,
            textvariable=self.username_var,
            width=30,
            font=self.theme.fonts["body"]
        )
        self.username_entry.pack(anchor="w", pady=(3, 0))
        
        # Password input
        password_container = tk.Frame(self.credential_frame)
        self.theme.apply_to_widget(password_container, "card")
        password_container.pack(fill=tk.X, padx=15, pady=(0, 10))
        
        password_label = self.theme.create_styled_label(
            password_container,
            "Password:",
            "body"
        )
        password_label.pack(anchor="w")
        
        self.password_entry = tk.Entry(
            password_container,
            textvariable=self.password_var,
            width=30,
            show="*",
            font=self.theme.fonts["body"]
        )
        self.password_entry.pack(anchor="w", pady=(3, 0))
    
    def _create_config_section(self) -> None:
        """Create configuration file section."""
        config_frame = tk.Frame(self.dialog)
        self.theme.apply_to_widget(config_frame, "card")
        config_frame.pack(fill=tk.X, padx=20, pady=(0, 5))
        
        # Section title
        config_title = self.theme.create_styled_label(
            config_frame,
            "Configuration",
            "heading"
        )
        config_title.pack(anchor="w", padx=15, pady=(10, 5))
        
        # Config file info
        config_info_frame = tk.Frame(config_frame)
        self.theme.apply_to_widget(config_info_frame, "card")
        config_info_frame.pack(fill=tk.X, padx=15, pady=(0, 5))
        
        info_text = f"Using configuration from:\n{self.config_path}"
        config_path_label = self.theme.create_styled_label(
            config_info_frame,
            info_text,
            "small",
            fg=self.theme.colors["text_secondary"],
            justify="left"
        )
        config_path_label.pack(anchor="w")
        
        # Config editor button
        config_button_frame = tk.Frame(config_frame)
        self.theme.apply_to_widget(config_button_frame, "card")
        config_button_frame.pack(fill=tk.X, padx=15, pady=(0, 10))
        
        edit_config_button = tk.Button(
            config_button_frame,
            text="⚙ Edit Configuration",
            command=self._open_config_editor
        )
        self.theme.apply_to_widget(edit_config_button, "button_secondary")
        edit_config_button.pack(side=tk.LEFT)
    
    def _create_button_panel(self) -> None:
        """Create dialog button panel."""
        button_frame = tk.Frame(self.dialog)
        self.theme.apply_to_widget(button_frame, "main_window")
        button_frame.pack(fill=tk.X, padx=20, pady=(5, 15))
        
        # Cancel button (left)
        cancel_button = tk.Button(
            button_frame,
            text="Cancel",
            command=self._cancel_scan
        )
        self.theme.apply_to_widget(cancel_button, "button_secondary")
        cancel_button.pack(side=tk.LEFT)
        
        # Start scan button (right)
        start_button = tk.Button(
            button_frame,
            text="🚀 Start Scan",
            command=self._start_scan
        )
        self.theme.apply_to_widget(start_button, "button_primary")
        start_button.pack(side=tk.RIGHT)
    
    def _setup_event_handlers(self) -> None:
        """Setup event handlers."""
        self.dialog.protocol("WM_DELETE_WINDOW", self._cancel_scan)
        
        # Keyboard shortcuts
        self.dialog.bind("<Return>", lambda e: self._start_scan())
        self.dialog.bind("<Escape>", lambda e: self._cancel_scan())
        
        # Country input validation
        self.country_var.trace_add("write", self._validate_country_input)
        
        # SMB1 toggle handler
        self.smb1_var.trace_add("write", self._on_smb1_var_changed)
    
    def _focus_country_field(self) -> None:
        """Set focus to country input field."""
        self.country_entry.focus_set()
    
    def _parse_and_validate_countries(self, country_input: str) -> tuple[list[str], str]:
        """Parse and validate comma-separated country codes.
        
        Args:
            country_input: Raw country input string
            
        Returns:
            Tuple of (valid_countries_list, error_message)
            If error_message is empty, validation succeeded
        """
        if not country_input.strip():
            return [], ""  # Empty input is valid (global scan)
        
        # Parse comma-separated countries
        countries = [country.strip().upper() for country in country_input.split(',')]
        valid_countries = []
        
        for country in countries:
            if not country:  # Skip empty entries from double commas
                continue
                
            # Validate individual country code
            if len(country) < 2 or len(country) > 3:
                return [], f"Invalid country code '{country}': must be 2-3 characters (e.g., US, GB, CA)"
            
            if not country.isalpha():
                return [], f"Invalid country code '{country}': must contain only letters (e.g., US, GB, CA)"
            
            valid_countries.append(country)
        
        if not valid_countries:
            return [], "Please enter at least one valid country code"
            
        return valid_countries, ""
    
    def _validate_country_input(self, *args) -> None:
        """Validate country code input in real-time."""
        country_input = self.country_var.get()
        
        # Allow empty (global scan)
        if not country_input.strip():
            return
        
        # Convert to uppercase but preserve formatting for user experience
        upper_input = country_input.upper()
        if upper_input != country_input:
            self.country_var.set(upper_input)
    
    def _on_smb1_var_changed(self, *args) -> None:
        """Handle SMB1 variable changes (for programmatic updates)."""
        self._update_security_controls()
    
    def _on_smb1_toggle(self) -> None:
        """Handle SMB1 checkbox toggle with consent validation."""
        if self.smb1_var.get():
            # User wants to enable SMB1 - show warning and get consent
            consent_given = show_smb1_warning_dialog(self.dialog)
            
            if consent_given:
                # User gave explicit consent
                self.smb1_enabled = True
                self.smb1_consent_given = True
                self._update_security_controls()
            else:
                # User declined - revert checkbox
                self.smb1_var.set(False)
                self.smb1_enabled = False
                self.smb1_consent_given = False
                self._update_security_controls()
        else:
            # User disabled SMB1 - return to safe defaults
            self.smb1_enabled = False
            self.smb1_consent_given = False
            self._update_security_controls()
    
    def _update_security_controls(self) -> None:
        """Update security controls based on SMB1 state."""
        if self.smb1_enabled:
            # SMB1 mode - anonymous only, update policy banner
            self.policy_banner.config(
                text="⚠️ Security Policy: SMB1 (NT1) • Anonymous-only • Discovery-only • Strict limits",
                bg='#fff3cd',  # Warning yellow background
                fg='#856404'   # Dark yellow text
            )
            self.policy_banner.master.config(bg='#fff3cd')
            
            # Disable and clear credential inputs
            self.username_entry.config(state=tk.DISABLED)
            self.password_entry.config(state=tk.DISABLED)
            self.username_var.set("")
            self.password_var.set("")
            
            # Add tooltip/explanation
            if hasattr(self, 'credential_frame'):
                # Update section title to show SMB1 restrictions
                for widget in self.credential_frame.winfo_children():
                    if isinstance(widget, tk.Label) and "Authentication" in widget.cget("text"):
                        widget.config(text="Authentication (Disabled for SMB1)", fg='#dc3545')
                        break
        else:
            # Normal mode - SMB2/3 with optional authentication
            self.policy_banner.config(
                text="🔒 Security Policy: SMB2/SMB3 only • Signing required • Safe by default",
                bg='#e8f5e8',  # Light green background
                fg='#155724'   # Dark green text
            )
            self.policy_banner.master.config(bg='#e8f5e8')
            
            # Enable credential inputs
            self.username_entry.config(state=tk.NORMAL)
            self.password_entry.config(state=tk.NORMAL)
            
            # Reset section title
            if hasattr(self, 'credential_frame'):
                for widget in self.credential_frame.winfo_children():
                    if isinstance(widget, tk.Label) and "Authentication" in widget.cget("text"):
                        widget.config(text="Authentication (Optional)", fg=self.theme.colors["text_primary"])
                        break
    
    def _open_config_editor(self) -> None:
        """Open configuration editor."""
        try:
            self.config_editor_callback(str(self.config_path))
        except Exception as e:
            messagebox.showerror(
                "Configuration Editor Error",
                f"Failed to open configuration editor:\n{str(e)}\n\n"
                "Please ensure the configuration system is properly set up."
            )
    
    def _start_scan(self) -> None:
        """Start the scan with configured parameters."""
        country_input = self.country_var.get().strip()
        
        # Parse and validate country codes
        countries, error_msg = self._parse_and_validate_countries(country_input)
        
        if error_msg:
            messagebox.showerror(
                "Invalid Country Code(s)",
                error_msg + "\n\nExamples:\n• Single: US\n• Multiple: US,GB,CA or US, GB, CA"
            )
            self.country_entry.focus_set()
            return
        
        # Check SMB1 consent if SMB1 is enabled
        if self.smb1_enabled and not self.smb1_consent_given:
            messagebox.showerror(
                "SMB1 Consent Required",
                "SMB1 mode requires explicit consent. Please toggle SMB1 option to provide consent."
            )
            return
        
        # Prepare scan parameters
        scan_params = {
            'countries': countries if countries else None,
            'smb1_enabled': self.smb1_enabled,
            'username': self.username_var.get().strip() if not self.smb1_enabled else None,
            'password': self.password_var.get().strip() if not self.smb1_enabled else None
        }
        
        # Prepare description for user confirmation
        if countries:
            if len(countries) == 1:
                scan_desc = f"country: {countries[0]}"
            else:
                scan_desc = f"countries: {', '.join(countries)}"
        else:
            scan_desc = "global (all countries)"
        
        # Add protocol information to description
        if self.smb1_enabled:
            protocol_desc = "SMB1 (Legacy Discovery Mode)"
            auth_desc = "anonymous authentication only"
        else:
            protocol_desc = "SMB2/SMB3 (Safe Mode)"
            if scan_params['username']:
                auth_desc = f"authenticated as '{scan_params['username']}'"
            else:
                auth_desc = "anonymous authentication"
            
        # Show comprehensive confirmation dialog
        confirmation_msg = (
            f"Start SMB security scan for {scan_desc}?\n\n"
            f"Protocol: {protocol_desc}\n"
            f"Authentication: {auth_desc}\n\n"
            "This will discover SMB servers and test for accessible shares."
        )
        
        if self.smb1_enabled:
            confirmation_msg += "\n\n⚠️ SMB1 mode will be automatically disabled after this scan."
        
        result = messagebox.askyesno("Start Scan", confirmation_msg)
        
        if result:
            try:
                # Set results and close dialog
                self.result = "start"
                self.scan_params = scan_params
                
                # Start the scan
                self.scan_start_callback(scan_params)
                
                # Close dialog
                self.dialog.destroy()
            except Exception as e:
                # Handle scan start errors gracefully
                messagebox.showerror(
                    "Scan Start Error",
                    f"Failed to start scan:\n{str(e)}\n\n"
                    "Please check that the backend is properly configured and try again."
                )
                # Don't close dialog so user can try again
    
    def _cancel_scan(self) -> None:
        """Cancel scan and close dialog."""
        self.result = "cancel"
        self.dialog.destroy()
    
    def show(self) -> Optional[str]:
        """
        Show dialog and wait for result.
        
        Returns:
            "start" if scan was started, "cancel" if cancelled, None if closed
        """
        # Wait for dialog to close
        self.parent.wait_window(self.dialog)
        return self.result


def show_scan_dialog(parent: tk.Widget, config_path: str,
                    config_editor_callback: Callable[[str], None],
                    scan_start_callback: Callable[[Dict[str, Any]], None]) -> Optional[str]:
    """
    Show enhanced scan configuration dialog with security controls.
    
    Args:
        parent: Parent widget
        config_path: Path to configuration file
        config_editor_callback: Function to open config editor
        scan_start_callback: Function to start scan with parameters dict
        
    Returns:
        Dialog result ("start", "cancel", or None)
    """
    dialog = ScanDialog(parent, config_path, config_editor_callback, scan_start_callback)
    return dialog.show()